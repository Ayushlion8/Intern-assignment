# KeyFrame Transcription API

Agent-first video/audio transcription service producing structured, speaker-diarized transcripts with language detection and English translation.

## What It Does

Submits short-form video/audio through a multi-stage pipeline:

1. **Whisper tiny** (local) — language detection
2. **Chirp 3** (Google Cloud Speech) — speaker diarization
3. **Gemini 2.5 Flash** (Vertex AI) — structured transcription with diarization context

Returns a `TranscriptionResult` with speaker-labeled segments, language codes, translations, and audio classification.

## Architecture

```
Video/Audio Input
       │
       ▼
┌──────────────────────────────────┐
│ 1. Whisper tiny (local, ~10ms)   │  Language detection
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│ 2. Chirp 3                       │  Speaker diarization
│                                  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│ 3. Gemini 2.5 Flash              │  Structured transcription
│    (Pro fallback if sparse)       │  with diarization context
└──────────────────────────────────┘
```

**API pattern**: POST to submit → get `job_id` → poll GET until completed. This polling approach works best for AI agents since it requires no special client capabilities.

## Quick Start

### Prerequisites

- Python 3.11+
- ffmpeg (`winget install ffmpeg`, `brew install ffmpeg`, or `apt install ffmpeg`)
- GCP service account with Speech-to-Text + Vertex AI APIs enabled

### Install

```bash
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Fill in GCP_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS
```

**Required environment variables:**

| Variable | Purpose |
|----------|---------|
| `GCP_PROJECT_ID` | GCP project ID (used for Gemini and Chirp 3) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON |

**Optional overrides:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `GCP_LOCATION` | `us-central1` | Vertex AI location |
| `GEMINI_TRANSCRIBE_MODEL_STRONG` | `gemini-2.5-flash` | Primary transcription model |
| `GEMINI_TRANSCRIBE_MODEL_PRO` | `gemini-2.5-pro` | Fallback transcription model |
| `GEMINI_RPM` | `15000` | Upstream Gemini rate limit |
| `CACHE_DIR` | `cache` | Transcript cache directory |
| `API_KEYS_FILE` | `api_keys.json` | API key storage file |

### Run the API Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Create an API Key

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "tier": "free"}'

# Via Python
python -c "from app.auth import create_key; print(create_key('my-agent', 'free'))"
```

### Transcribe a Video

```bash
# Submit
curl -X POST http://localhost:8000/api/v1/transcribe \
  -H "X-API-Key: kf_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/video.mp4"}'

# Poll for result
curl http://localhost:8000/api/v1/jobs/JOB_ID \
  -H "X-API-Key: kf_YOUR_KEY"
```

### CLI (Original Pipeline)

```bash
python transcribe.py video.mp4
python transcribe.py https://example.com/video.mp4 --json
python transcribe.py video.mp4 --model gemini-2.5-pro
```

## API Endpoints

### Transcription

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/transcribe` | Submit URL for transcription |
| `POST` | `/api/v1/transcribe/upload` | Upload file for transcription (max 100 MB) |
| `GET` | `/api/v1/jobs/{job_id}` | Poll job status and retrieve results |

### Account

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/keys` | Create an API key |
| `GET` | `/api/v1/keys` | List all API keys |
| `GET` | `/api/v1/usage` | Get usage and remaining quota |

### System & Agent Discovery

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/openapi.json` | Full OpenAPI specification |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |
| `GET` | `/llms.txt` | Agent discoverability (emerging standard) |
| `GET` | `/llms-full.txt` | Full agent documentation |
| `GET` | `/.well-known/ai-plugin.json` | AI plugin manifest |
| `GET` | `/.well-known/mcp` | MCP server connection info |

## Pricing

| Tier | Monthly Quota | Price/Video | Rate Limit |
|------|--------------|-------------|------------|
| Free | 5 | $0.00 | 5 RPM |
| Starter | 100 | $0.10 | 30 RPM |
| Pro | 1,000 | $0.08 | 60 RPM |
| Enterprise | Unlimited | $0.06 | 120 RPM |

Pipeline cost: ~$0.02–0.08 per video. See [DECISIONS.md](DECISIONS.md) for pricing rationale.

## Output Schema

```json
{
  "text": "Full English transcript...",
  "diarizedTranscript": [
    {
      "speaker": "creator",
      "text": "English translation",
      "originalText": "Original language text",
      "language": "ko",
      "languageName": "Korean"
    }
  ],
  "audioMode": "spoken-narration",
  "detectedLanguage": "ko",
  "detectedLanguageName": "Korean",
  "languagesUsed": ["ko", "en"],
  "languagesUsedNames": ["Korean", "English"],
  "isTranslated": true
}
```

Speaker labels: `creator`, `ai`, `narrator`, `on-screen-ocr`, `person1`..`personN`, `other`

## Error Handling

All errors return a structured response:

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

Error actions: `retry`, `reduce_file_size`, `check_auth`, `wait_and_retry`, `upgrade_plan`, `contact_support`

## MCP Server

The Model Context Protocol server lets AI agents use transcription as a tool:

```bash
# Set environment
export KEYFRAME_API_URL=http://localhost:8000
export KEYFRAME_API_KEY=kf_YOUR_KEY

# Run
python mcp_server.py
```

Tools exposed: `transcribe`, `get_job`, `create_api_key`, `check_usage`, `health_check`

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application, routes, middleware
│   ├── auth.py           # API key management, pricing tiers
│   ├── jobs.py           # Background job manager
│   └── errors.py         # Agent-optimized error responses
├── tests/
│   ├── __init__.py
│   └── test_api.py       # API integration tests
├── transcribe.py         # Core transcription pipeline + CLI
├── schemas.py            # Pydantic models + Gemini prompt
├── config.py             # API client factories, usage tracker, retry logic
├── rate_limiter.py       # Token-bucket rate limiter (upstream)
├── mcp_server.py         # MCP server for AI agent integration
├── Dockerfile            # Container build
├── .env.example          # Environment variable template
├── .gitignore
├── requirements.txt
├── DECISIONS.md          # Design decisions and rationale
├── TASK.md               # Assignment brief
└── README.md             # This file
```

## Testing

```bash
python -m pytest tests/ -v
```

## Deployment

The service is designed for deployment on Railway, Render, or any Docker-capable host:

```bash
# Build and run locally
docker build -t keyframe-api .
docker run -p 8000:8000 --env-file .env keyframe-api
```

See [DECISIONS.md](DECISIONS.md) for deployment rationale.

## Assumptions

1. Single-instance deployment (in-memory job store; scale out with Redis if needed)
2. Short-form video (~5 min max); longer videos may timeout
3. Users provide their own GCP credentials
4. Free-tier key creation is open (add verification for production)
5. Monthly usage tracking resets in-memory (integrate Stripe for production billing)
