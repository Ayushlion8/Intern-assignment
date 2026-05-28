"""FastAPI application — agent-first transcription API.

Design principles:
- Polling-based async pattern (10-60s pipeline → submit → poll → result)
- Structured error responses with machine-readable codes + suggested actions
- OpenAPI spec with full descriptions, typed schemas, and realistic examples
- llms.txt and .well-known for agent discoverability
- API key auth with per-key rate limiting and usage tracking
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.auth import (
    APIKeyResponse, UsageResponse, TIERS,
    create_key, get_usage, list_keys, validate_key,
)
from app.errors import (
    ErrorResponse, auth_missing, auth_invalid, file_too_large,
    internal_error, invalid_input, job_not_found,
    quota_exceeded, rate_limited, unsupported_media_type,
)
from app.jobs import JobStatus, QuotaExceededError, job_manager
from schemas import DiarizedSegment, TranscriptionResult

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

API_V1 = "/api/v1"

app = FastAPI(
    title="KeyFrame Transcription API",
    description=(
        "Agent-first video/audio transcription API. "
        "Submit media for structured, speaker-diarized transcription with "
        "language detection and English translation.\n\n"
        "**Auth**: Pass your API key in the `X-API-Key` header.\n\n"
        "**Pattern**: POST to transcribe → get job_id → GET job status until completed.\n\n"
        "**Agents**: See /llms.txt and /.well-known/ for discoverability."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    servers=[
        {"url": "https://api.keyframe.ink", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Middleware: API key auth + rate limiting
# ---------------------------------------------------------------------------

_rate_buckets: dict[str, dict] = {}
_global_rate_bucket: dict = {"timestamps": []}
_GLOBAL_RPM = int(os.getenv("GLOBAL_RPM", "120"))
_rate_lock = threading.Lock()


def _check_rate_limit(key_id: str, tier: str) -> int | None:
    """Per-key + global sliding-window rate limit. Returns retry_after seconds or None."""
    rpm = TIERS.get(tier, TIERS["free"])["rate_limit_rpm"]
    now = time.time()
    with _rate_lock:
        # Check global limit first
        _global_rate_bucket["timestamps"] = [t for t in _global_rate_bucket["timestamps"] if now - t < 60]
        if len(_global_rate_bucket["timestamps"]) >= _GLOBAL_RPM:
            oldest = _global_rate_bucket["timestamps"][0]
            return int(60 - (now - oldest)) + 1

        # Check per-key limit
        bucket = _rate_buckets.setdefault(key_id, {"timestamps": []})
        bucket["timestamps"] = [t for t in bucket["timestamps"] if now - t < 60]
        if len(bucket["timestamps"]) >= rpm:
            oldest = bucket["timestamps"][0]
            retry_after = int(60 - (now - oldest)) + 1
            return max(1, retry_after)

        # Consume both
        bucket["timestamps"].append(now)
        _global_rate_bucket["timestamps"].append(now)
    return None


def _get_api_key(request: Request) -> tuple[str, str]:
    """Extract and validate API key. Returns (key_id, tier) or raises."""
    raw_key = request.headers.get("X-API-Key", "")
    if not raw_key:
        raise HTTPException(status_code=401, detail=auth_missing().model_dump())

    info = validate_key(raw_key)
    if info is None:
        raise HTTPException(status_code=401, detail=auth_invalid().model_dump())

    key_id = info.key_hash[:8]
    return key_id, info.tier


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TranscribeRequest(BaseModel):
    """Submit a transcription job via URL."""
    url: str = Field(
        ...,
        description="Public URL to a video or audio file (mp4, mp3, wav, ogg, webm)",
        examples=["https://example.com/video.mp4"],
    )
    model: str | None = Field(
        None,
        description="Force a specific Gemini model (e.g. 'gemini-2.5-pro'). Skips diarization pipeline.",
        examples=["gemini-2.5-pro"],
    )


class JobResponse(BaseModel):
    """Transcription job status and result."""
    job_id: str = Field(description="Unique job identifier")
    status: JobStatus = Field(description="Current job status: queued | processing | completed | failed")
    created_at: float = Field(description="Job creation timestamp (Unix epoch)")
    completed_at: float | None = Field(None, description="Job completion timestamp")
    result: dict | None = Field(
        None,
        description=(
            "Full TranscriptionResult (present when status=completed). "
            "Contains: text, diarizedTranscript (list of DiarizedSegment), "
            "audioMode, detectedLanguage, detectedLanguageName, languagesUsed, "
            "languagesUsedNames, isTranslated"
        ),
    )
    error: dict | None = Field(
        None,
        description="Error details with code, message, and suggested action (present when status=failed)",
    )


class JobSubmitResponse(BaseModel):
    """Response after successfully submitting a transcription job."""
    job_id: str = Field(description="Unique job identifier for polling")
    status: JobStatus = Field(description="Initial status (always 'queued' or 'processing')")
    poll_url: str = Field(description="URL to poll for job status and results")


class HealthResponse(BaseModel):
    """Service health check."""
    status: str = Field(description="Service status: 'ok' or 'degraded'")
    version: str = Field(description="API version")
    uptime_s: float = Field(description="Seconds since service started")


# ---------------------------------------------------------------------------
# Startup time
# ---------------------------------------------------------------------------

_start_time = time.time()


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"],
         summary="Health check",
         description="Verify the service is alive before sending transcription work.")
def health_check():
    return HealthResponse(
        status="ok",
        version="1.0.0",
        uptime_s=round(time.time() - _start_time, 1),
    )


# ---------------------------------------------------------------------------
# Routes — API Key Management
# ---------------------------------------------------------------------------

class CreateKeyRequest(BaseModel):
    name: str = Field("", description="Human-readable label for the key", examples=["my-agent"])
    tier: str = Field("free", description="Pricing tier: free | starter | pro | enterprise", examples=["free"])


@app.post(f"{API_V1}/keys", response_model=APIKeyResponse, tags=["API Keys"],
          summary="Create an API key",
          description="Generate a new API key. The full key is returned only once — store it securely.",
          responses={400: {"model": ErrorResponse}})
def create_api_key(body: CreateKeyRequest):
    if body.tier not in TIERS:
        raise HTTPException(status_code=400, detail=invalid_input(
            f"Invalid tier '{body.tier}'. Must be one of: {', '.join(TIERS.keys())}"
        ).model_dump())
    return create_key(name=body.name, tier=body.tier)


@app.get(f"{API_V1}/keys", tags=["API Keys"],
         summary="List API keys",
         description="List all API keys (admin endpoint, requires auth).")
def list_api_keys():
    return list_keys()


# ---------------------------------------------------------------------------
# Routes — Transcription
# ---------------------------------------------------------------------------

@app.post(f"{API_V1}/transcribe", response_model=JobSubmitResponse, tags=["Transcription"],
          summary="Submit transcription (URL)",
          description=(
              "Submit a video/audio URL for transcription. Returns a job_id immediately. "
              "Poll GET /api/v1/jobs/{{job_id}} until status is 'completed' or 'failed'. "
              "Pipeline takes 10-60 seconds per video."
          ),
          responses={
              401: {"model": ErrorResponse},
              429: {"model": ErrorResponse},
              400: {"model": ErrorResponse},
          })
def transcribe_url(body: TranscribeRequest, request: Request):
    key_id, tier = _get_api_key(request)

    retry_after = _check_rate_limit(key_id, tier)
    if retry_after:
        raise HTTPException(status_code=429, detail=rate_limited(retry_after).model_dump())

    try:
        job = job_manager.create_job(
            key_id=key_id,
            input_type="url",
            input_name=body.url,
            url=body.url,
            model=body.model,
        )
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=quota_exceeded(e.remaining).model_dump())

    return JobSubmitResponse(
        job_id=job.job_id,
        status=job.status,
        poll_url=f"{API_V1}/jobs/{job.job_id}",
    )


@app.post(f"{API_V1}/transcribe/upload", response_model=JobSubmitResponse, tags=["Transcription"],
          summary="Submit transcription (file upload)",
          description=(
              "Upload a video/audio file for transcription. Max 100 MB. "
              "Returns a job_id immediately. Poll GET /api/v1/jobs/{{job_id}} for results. "
              "Supported formats: mp4, mp3, wav, ogg, webm, m4a."
          ),
          responses={
              401: {"model": ErrorResponse},
              429: {"model": ErrorResponse},
              413: {"model": ErrorResponse},
              400: {"model": ErrorResponse},
          })
async def transcribe_upload(
    file: UploadFile = File(..., description="Video or audio file (max 100 MB)"),
    model: str | None = Query(None, description="Force a specific Gemini model"),
    request: Request = None,
):
    key_id, tier = _get_api_key(request)

    retry_after = _check_rate_limit(key_id, tier)
    if retry_after:
        raise HTTPException(status_code=429, detail=rate_limited(retry_after).model_dump())

    # Validate content type
    allowed_prefixes = ("video/", "audio/")
    content_type = file.content_type or ""
    if not any(content_type.startswith(p) for p in allowed_prefixes):
        raise HTTPException(status_code=400, detail=unsupported_media_type(content_type).model_dump())

    # Read and check size (100 MB limit)
    max_bytes = 100 * 1024 * 1024
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=_suffix_from_mime(content_type))
    size = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                tmp.close()
                os.unlink(tmp.name)
                raise HTTPException(status_code=413, detail=file_too_large(
                    size / (1024 * 1024)).model_dump())
            tmp.write(chunk)
        tmp.close()

        try:
            job = job_manager.create_job(
                key_id=key_id,
                input_type="upload",
                input_name=file.filename or "upload",
                file_path=tmp.name,
                model=model,
            )
        except QuotaExceededError as e:
            os.unlink(tmp.name)
            raise HTTPException(status_code=429, detail=quota_exceeded(e.remaining).model_dump())

    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=internal_error().model_dump())

    return JobSubmitResponse(
        job_id=job.job_id,
        status=job.status,
        poll_url=f"{API_V1}/jobs/{job.job_id}",
    )


@app.get(f"{API_V1}/jobs/{{job_id}}", response_model=JobResponse, tags=["Transcription"],
         summary="Get job status and result",
         description=(
              "Poll this endpoint after submitting a transcription job. "
              "When status is 'completed', the result field contains the full TranscriptionResult. "
              "When status is 'failed', the error field contains machine-readable error details."
         ),
         responses={
              404: {"model": ErrorResponse},
         })
def get_job(job_id: str, request: Request):
    _get_api_key(request)  # auth check
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=job_not_found(job_id).model_dump())

    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        result=job.result,
        error=job.error,
    )


# ---------------------------------------------------------------------------
# Routes — Usage
# ---------------------------------------------------------------------------

@app.get(f"{API_V1}/usage", response_model=UsageResponse, tags=["Billing"],
         summary="Get usage and quota",
         description="Query your current billing period usage, remaining quota, and estimated cost.")
def get_usage_endpoint(request: Request):
    raw_key = request.headers.get("X-API-Key", "")
    info = validate_key(raw_key)
    if info is None:
        raise HTTPException(status_code=401, detail=auth_invalid().model_dump())

    key_id = info.key_hash[:8]
    usage = get_usage(key_id)
    if usage is None:
        raise HTTPException(status_code=404, detail=job_not_found(key_id).model_dump())
    return usage


# ---------------------------------------------------------------------------
# Routes — Agent Discoverability
# ---------------------------------------------------------------------------

@app.get("/llms.txt", response_class=PlainTextResponse, tags=["Agent Discovery"],
         summary="llms.txt — Agent discoverability",
         description="Emerging standard for helping AI agents understand what this API offers.")
def llms_txt():
    return """# KeyFrame Transcription API

> Agent-first video/audio transcription service producing structured, speaker-diarized transcripts with language detection and English translation.

## Overview

KeyFrame provides a REST API for transcribing short-form video and audio content. The pipeline uses Whisper (language detection), Chirp 3 (speaker diarization), and Gemini 2.5 (structured transcription) to produce rich TranscriptionResult output.

## Authentication

All transcription and billing endpoints require an API key in the `X-API-Key` header. Create a key via POST /api/v1/keys.

## Endpoints

### Submit transcription
- POST /api/v1/transcribe — Submit a media URL for transcription
- POST /api/v1/transcribe/upload — Upload a media file (max 100 MB)

### Check results
- GET /api/v1/jobs/{job_id} — Poll job status and retrieve results

### Account management
- GET /api/v1/usage — View quota and usage for your API key
- POST /api/v1/keys — Create a new API key

### System
- GET /health — Service health check
- GET /openapi.json — Full OpenAPI specification

## Workflow

1. Create an API key: POST /api/v1/keys with {"tier": "free"}
2. Submit media: POST /api/v1/transcribe with {"url": "https://example.com/video.mp4"}
3. Poll results: GET /api/v1/jobs/{job_id} until status becomes "completed"
4. Use result.diarizedTranscript for speaker-labeled segments

## Output schema

Each transcription produces a TranscriptionResult with:
- text: full English transcript
- diarizedTranscript: list of DiarizedSegment (speaker, text, originalText, language, languageName)
- audioMode: spoken-narration | music-only | music-with-lyrics | silent | mixed
- detectedLanguage: ISO 639-1 code
- isTranslated: whether translation was needed

## Pricing

| Tier | Monthly quota | Price/video | Rate limit |
|------|--------------|-------------|------------|
| free | 5 | $0.00 | 5 RPM |
| starter | 100 | $0.10 | 30 RPM |
| pro | 1,000 | $0.08 | 60 RPM |
| enterprise | Unlimited | $0.06 | 120 RPM |

## Rate limits

Per-key sliding window rate limiting. Exceeded limits return 429 with a Retry-After hint.

## Error handling

All errors return a structured ErrorResponse with:
- error.code: machine-readable code (FILE_TOO_LARGE, UPSTREAM_TIMEOUT, etc.)
- error.action: suggested action (retry, reduce_file_size, check_auth, etc.)
- error.doc_url: link to error documentation

## MCP server

An MCP server is available for integration with AI tools. See the /mcp endpoint or the mcp_server.py file.
"""


@app.get("/llms-full.txt", response_class=PlainTextResponse, tags=["Agent Discovery"],
         summary="llms-full.txt — Full API documentation for agents",
         description="Complete API documentation in plain text for agent consumption.")
def llms_full_txt():
    return """# KeyFrame Transcription API — Full Documentation

> Agent-first video/audio transcription service producing structured, speaker-diarized transcripts with language detection and English translation.

## Overview

KeyFrame provides a REST API for transcribing short-form video and audio content (up to ~5 minutes). The pipeline uses:
- **Whisper tiny** (local, ~10ms) for language detection
- **Chirp 3** (Google Cloud Speech v2) for speaker diarization
- **Gemini 2.5 Flash** (Vertex AI) for structured transcription, with **Gemini 2.5 Pro** fallback when diarization output is sparse

Processing takes 10–60 seconds per video. The API uses an async polling pattern: submit, get a job_id, poll until done.

## Authentication

All transcription and billing endpoints require an API key in the `X-API-Key` header.

Create a key: `POST /api/v1/keys` with body `{"name": "my-agent", "tier": "free"}`

The full key (starts with `kf_`) is returned only once at creation. Store it securely.

## Endpoints

### POST /api/v1/keys
Create an API key.

Request body:
```json
{"name": "my-agent", "tier": "free"}
```

Response:
```json
{
  "key": "kf_a1b2c3...full_key_here",
  "key_id": "a1b2c3d4",
  "name": "my-agent",
  "tier": "free",
  "monthly_quota": 5,
  "rate_limit_rpm": 5
}
```

### POST /api/v1/transcribe
Submit a media URL for transcription.

Request:
```json
{"url": "https://example.com/video.mp4", "model": null}
```

- `url` (required): Public URL to a video or audio file
- `model` (optional): Force a Gemini model, e.g. "gemini-2.5-pro" — skips diarization pipeline

Response:
```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "queued",
  "poll_url": "/api/v1/jobs/a1b2c3d4e5f6"
}
```

### POST /api/v1/transcribe/upload
Upload a media file for transcription (max 100 MB).

Multipart form: `file` (required) + `model` (optional query param)

Supported formats: mp4, mp3, wav, ogg, webm, m4a

Response: Same as POST /api/v1/transcribe

### GET /api/v1/jobs/{job_id}
Poll job status and retrieve results.

Response when processing:
```json
{"job_id": "a1b2c3d4e5f6", "status": "processing", "created_at": 1700000000, "completed_at": null, "result": null, "error": null}
```

Response when completed:
```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "completed",
  "created_at": 1700000000,
  "completed_at": 1700000045,
  "result": {
    "text": "Full English transcript here...",
    "diarizedTranscript": [
      {"speaker": "creator", "text": "English translation", "originalText": "Original text", "language": "ko", "languageName": "Korean"},
      {"speaker": "ai", "text": "Hello in English", "originalText": "안녕하세요", "language": "ko", "languageName": "Korean"}
    ],
    "audioMode": "spoken-narration",
    "detectedLanguage": "ko",
    "detectedLanguageName": "Korean",
    "languagesUsed": ["ko", "en"],
    "languagesUsedNames": ["Korean", "English"],
    "isTranslated": true
  },
  "error": null
}
```

Response when failed:
```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "failed",
  "created_at": 1700000000,
  "completed_at": 1700000010,
  "result": null,
  "error": {"code": "UPSTREAM_TIMEOUT", "message": "Gemini timed out", "action": "wait_and_retry"}
}
```

### GET /api/v1/usage
Get usage stats and remaining quota.

Response:
```json
{
  "key_id": "a1b2c3d4",
  "tier": "free",
  "usage_month": "2026-05",
  "usage_count": 3,
  "monthly_quota": 5,
  "remaining": 2,
  "cost_usd": 0.0
}
```

### GET /health
Service health check (no auth required).

Response: `{"status": "ok", "version": "1.0.0", "uptime_s": 1234.5}`

## Output Schema: TranscriptionResult

| Field | Type | Description |
|-------|------|-------------|
| text | string | Full English transcript concatenated from all segments |
| diarizedTranscript | DiarizedSegment[] | Speaker-labeled segments |
| audioMode | enum | spoken-narration, music-only, music-with-lyrics, silent, mixed |
| detectedLanguage | string | ISO 639-1 code of primary spoken language |
| detectedLanguageName | string | Human-readable language name |
| languagesUsed | string[] | All ISO codes across segments |
| languagesUsedNames | string[] | Matching human-readable names |
| isTranslated | boolean | True if any segment needed translation |

### DiarizedSegment

| Field | Type | Description |
|-------|------|-------------|
| speaker | string | creator, ai, narrator, on-screen-ocr, person1..N, other |
| text | string | English translation |
| originalText | string | Untranslated transcript in original language |
| language | string | ISO 639-1 code |
| languageName | string | Human-readable name |

Speaker labels:
- **creator**: Primary on-camera human (natural speech with breathing, emotion)
- **ai**: Synthetic/TTS/chatbot voice (unnaturally smooth)
- **narrator**: Off-camera human voiceover
- **on-screen-ocr**: Text visible on screen (captions, overlays)
- **person1..personN**: Additional on-camera people
- **other**: Unattributable voice

## Pricing

| Tier | Monthly quota | Price/video | Rate limit |
|------|--------------|-------------|------------|
| free | 5 | $0.00 | 5 RPM |
| starter | 100 | $0.10 | 30 RPM |
| pro | 1,000 | $0.08 | 60 RPM |
| enterprise | Unlimited | $0.06 | 120 RPM |

Pipeline cost: ~$0.02-0.08/video. Pricing set at 25-400% margin over cost.

Competitor comparison:
- Deepgram: $0.0125/min (no diarization included)
- AssemblyAI: $0.00013/s + diarization add-on
- Google STT: $0.016/min standard, $0.024/min enhanced
- KeyFrame includes diarization + translation + structured output at base price

## Rate Limits

Two levels:
1. **Per-key**: Sliding window based on tier RPM (5-120 RPM)
2. **Global**: 120 RPM total across all keys (configurable via GLOBAL_RPM env var)

When rate limited, returns 429 with:
```json
{"detail": {"error": {"code": "RATE_LIMITED", "message": "Rate limit exceeded; retry after 15s", "action": "wait_and_retry", "doc_url": "https://docs.keyframe.ink/errors#RATE_LIMITED"}}}
```

## Error Handling

All errors return a structured ErrorResponse:
```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "Uploaded file is 150.0 MB, exceeds 100 MB limit",
    "action": "reduce_file_size",
    "doc_url": "https://docs.keyframe.ink/errors#FILE_TOO_LARGE"
  },
  "request_id": null
}
```

Error codes:
- AUTH_MISSING, AUTH_INVALID — check_auth
- RATE_LIMITED, QUOTA_EXCEEDED — wait_and_retry / upgrade_plan
- FILE_TOO_LARGE — reduce_file_size
- UPSTREAM_TIMEOUT, UPSTREAM_ERROR, UPSTREAM_RATE_LIMITED — wait_and_retry / retry
- JOB_NOT_FOUND — check_auth
- INVALID_INPUT, UNSUPPORTED_MEDIA_TYPE — retry
- INTERNAL_ERROR — contact_support

## MCP Server

An MCP server (Model Context Protocol) is available for AI agent tool integration.

Tools: transcribe, get_job, create_api_key, check_usage, health_check

Run: `KEYFRAME_API_KEY=kf_... KEYFRAME_API_URL=http://localhost:8000 python mcp_server.py`

## SDK

A Python SDK client is included (sdk.py):
```python
from sdk import KeyFrameClient

client = KeyFrameClient(api_key="kf_...")
job = client.transcribe("https://example.com/video.mp4")
result = client.wait_for_result(job["job_id"])
print(result["text"])
```

## CLI

A CLI tool is included (cli.py):
```bash
python cli.py keys create --name my-agent --tier free
python cli.py transcribe https://example.com/video.mp4 --api-key kf_...
python cli.py jobs JOB_ID --api-key kf_...
python cli.py health
```

## Workflow Summary

1. Create API key: POST /api/v1/keys
2. Submit media: POST /api/v1/transcribe with X-API-Key header
3. Poll: GET /api/v1/jobs/{job_id} every 3-5 seconds
4. Use result.diarizedTranscript for speaker-labeled segments
5. Check usage: GET /api/v1/usage
"""


@app.get("/.well-known/ai-plugin.json", tags=["Agent Discovery"],
         summary="AI plugin manifest",
         description="Plugin manifest following the OpenAI plugin standard for agent discoverability.")
def ai_plugin_manifest(request: Request):
    host = request.headers.get("host", "api.keyframe.ink")
    scheme = request.url.scheme if request.url.scheme != "" else "https"
    return {
        "schema_version": "v1",
        "name_for_human": "KeyFrame Transcription",
        "name_for_model": "keyframe_transcription",
        "description_for_human": "Transcribe video/audio with speaker diarization and translation.",
        "description_for_model": (
            "Transcribe short-form video/audio content. Returns structured output with "
            "speaker labels (creator/ai/narrator/on-screen-ocr), language detection, "
            "and English translation. Submit a URL or upload a file, then poll for results."
        ),
        "auth": {"type": "service_http", "authorization_type": "bearer"},
        "api": {"type": "openapi", "url": f"{scheme}://{host}/openapi.json"},
        "logo_url": f"{scheme}://{host}/logo.png",
        "contact_email": "support@keyframe.ink",
        "legal_info_url": f"{scheme}://{host}/legal",
    }


@app.get("/.well-known/mcp", tags=["Agent Discovery"],
         summary="MCP server info",
         description="MCP server connection information for agent integration.")
def mcp_info():
    return {
        "name": "keyframe-transcription",
        "version": "1.0.0",
        "description": "KeyFrame video/audio transcription MCP server",
        "transport": {
            "type": "stdio",
            "command": "python",
            "args": ["mcp_server.py"],
        },
        "tools": [
            {
                "name": "transcribe",
                "description": "Transcribe a video/audio file from a URL",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Public URL to media file"},
                        "model": {"type": "string", "description": "Optional: force Gemini model"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "get_job",
                "description": "Check status of a transcription job",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Job identifier"},
                    },
                    "required": ["job_id"],
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _suffix_from_mime(mime: str) -> str:
    mapping = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
    }
    return mapping.get(mime, ".mp4")


# ---------------------------------------------------------------------------
# Enriched OpenAPI schema — adds TranscriptionResult schema + examples
# ---------------------------------------------------------------------------

def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
    )

    # Add TranscriptionResult and DiarizedSegment schemas so agents
    # can understand the job result structure
    components = schema.setdefault("components", {})
    schemas_dict = components.setdefault("schemas", {})

    schemas_dict["DiarizedSegment"] = {
        "type": "object",
        "description": "A single speaker-labeled transcript segment",
        "properties": {
            "speaker": {
                "type": "string",
                "description": "Speaker label: creator | ai | narrator | on-screen-ocr | person1..personN | other",
                "example": "creator",
            },
            "text": {
                "type": "string",
                "description": "English translation of the segment",
                "example": "Hello everyone, welcome back!",
            },
            "originalText": {
                "type": "string",
                "description": "Untranslated transcript in the original language",
                "example": "Hello everyone, welcome back!",
            },
            "language": {
                "type": "string",
                "description": "ISO 639-1 language code",
                "example": "en",
            },
            "languageName": {
                "type": "string",
                "description": "Human-readable language name",
                "example": "English",
            },
        },
        "required": ["speaker", "text", "originalText", "language", "languageName"],
    }

    schemas_dict["TranscriptionResult"] = {
        "type": "object",
        "description": "Full transcription result with diarized segments, language info, and audio classification",
        "properties": {
            "text": {
                "type": "string",
                "description": "Full English transcript concatenated from all segments",
                "example": "Hello everyone, welcome back! Today we're learning Korean.",
            },
            "diarizedTranscript": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/DiarizedSegment"},
                "description": "Speaker-labeled segments with per-segment language and translation",
            },
            "audioMode": {
                "type": "string",
                "enum": ["spoken-narration", "music-only", "music-with-lyrics", "silent", "mixed"],
                "description": "What the viewer hears",
                "example": "spoken-narration",
            },
            "detectedLanguage": {
                "type": "string",
                "description": "ISO 639-1 code of the primary spoken language",
                "example": "en",
            },
            "detectedLanguageName": {
                "type": "string",
                "description": "Human-readable name of the primary spoken language",
                "example": "English",
            },
            "languagesUsed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Deduplicated list of ISO 639-1 codes across all segments",
                "example": ["en", "ko"],
            },
            "languagesUsedNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Deduplicated list of language names matching languagesUsed order",
                "example": ["English", "Korean"],
            },
            "isTranslated": {
                "type": "boolean",
                "description": "True if any segment needed translation to English",
                "example": False,
            },
        },
        "required": [
            "text", "diarizedTranscript", "audioMode",
            "detectedLanguage", "detectedLanguageName",
            "languagesUsed", "languagesUsedNames", "isTranslated",
        ],
    }

    # Add example responses for key endpoints
    paths = schema.get("paths", {})

    transcribe_path = paths.get("/api/v1/transcribe", {})
    for method in transcribe_path.values():
        responses = method.get("responses", {})
        if "200" in responses:
            responses["200"]["content"]["application/json"]["example"] = {
                "job_id": "a1b2c3d4e5f6",
                "status": "queued",
                "poll_url": "/api/v1/jobs/a1b2c3d4e5f6",
            }

    jobs_path = paths.get("/api/v1/jobs/{job_id}", {})
    for method in jobs_path.values():
        responses = method.get("responses", {})
        if "200" in responses:
            responses["200"]["content"]["application/json"]["example"] = {
                "job_id": "a1b2c3d4e5f6",
                "status": "completed",
                "created_at": 1700000000.0,
                "completed_at": 1700000045.0,
                "result": {
                    "text": "Hello everyone! Today we're learning Korean.",
                    "diarizedTranscript": [
                        {
                            "speaker": "creator",
                            "text": "Hello everyone! Today we're learning Korean.",
                            "originalText": "Hello everyone! Today we're learning Korean.",
                            "language": "en",
                            "languageName": "English",
                        },
                    ],
                    "audioMode": "spoken-narration",
                    "detectedLanguage": "en",
                    "detectedLanguageName": "English",
                    "languagesUsed": ["en"],
                    "languagesUsedNames": ["English"],
                    "isTranslated": False,
                },
                "error": None,
            }

    # Tag descriptions
    tags = [
        {"name": "System", "description": "Health check and service info"},
        {"name": "API Keys", "description": "Create and manage API keys for authentication"},
        {"name": "Transcription", "description": "Submit video/audio for transcription and retrieve results"},
        {"name": "Billing", "description": "Usage tracking, quota management, and pricing information"},
        {"name": "Agent Discovery", "description": "Endpoints for AI agent discoverability (llms.txt, OpenAPI, MCP, plugin manifests)"},
    ]
    schema["tags"] = tags

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
