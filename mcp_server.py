"""MCP (Model Context Protocol) server for KeyFrame Transcription API.

Exposes the transcription pipeline as MCP tools that AI agents can discover
and use through the Model Context Protocol standard.

Run: python mcp_server.py
Requires: pip install mcp
"""

from __future__ import annotations

import json
import os
import sys

# MCP SDK
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP(
    "keyframe-transcription",
    version="1.0.0",
    description="KeyFrame video/audio transcription — structured, speaker-diarized transcripts with translation",
)


# ---------------------------------------------------------------------------
# Configuration — connect to the running API or run the pipeline directly
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("KEYFRAME_API_URL", "http://localhost:8000")
API_KEY = os.getenv("KEYFRAME_API_KEY", "")


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def transcribe(url: str, model: str | None = None) -> str:
    """Transcribe a video or audio file from a public URL.

    Submits the URL for processing and returns a job_id.
    Use get_job() to poll for results.

    Args:
        url: Public URL to a video or audio file (mp4, mp3, wav, ogg, webm)
        model: Optional — force a specific Gemini model (e.g. 'gemini-2.5-pro')
    """
    import requests as http_requests

    body = {"url": url}
    if model:
        body["model"] = model

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v1/transcribe",
        json=body,
        headers=_headers(),
        timeout=30,
    )

    if resp.status_code == 401:
        return "Error: Invalid or missing API key. Set KEYFRAME_API_KEY environment variable."
    if resp.status_code == 429:
        data = resp.json()
        action = data.get("error", {}).get("action", "wait_and_retry")
        return f"Error: Rate limited. Suggested action: {action}"
    if resp.status_code != 200:
        return f"Error: API returned {resp.status_code}: {resp.text[:200]}"

    data = resp.json()
    return json.dumps({
        "job_id": data["job_id"],
        "status": data["status"],
        "poll_url": data["poll_url"],
        "next_step": f"Call get_job(job_id='{data['job_id']}') to check status and retrieve results",
    })


@mcp.tool()
def get_job(job_id: str) -> str:
    """Check the status of a transcription job and retrieve results.

    Call this after transcribe() to poll for results.
    When status is 'completed', the result contains the full TranscriptionResult.
    When status is 'failed', the error field contains details.

    Args:
        job_id: The job identifier returned by transcribe()
    """
    import requests as http_requests

    resp = http_requests.get(
        f"{API_BASE_URL}/api/v1/jobs/{job_id}",
        headers=_headers(),
        timeout=30,
    )

    if resp.status_code == 401:
        return "Error: Invalid or missing API key."
    if resp.status_code == 404:
        return f"Error: Job {job_id} not found."
    if resp.status_code != 200:
        return f"Error: API returned {resp.status_code}: {resp.text[:200]}"

    data = resp.json()
    status = data.get("status")

    if status == "completed" and data.get("result"):
        result = data["result"]
        summary = {
            "job_id": job_id,
            "status": "completed",
            "detected_language": result.get("detectedLanguage", ""),
            "audio_mode": result.get("audioMode", ""),
            "is_translated": result.get("isTranslated", False),
            "full_text": result.get("text", ""),
            "segments": [
                {
                    "speaker": s.get("speaker", ""),
                    "text": s.get("text", ""),
                    "original_text": s.get("originalText", ""),
                    "language": s.get("language", ""),
                }
                for s in result.get("diarizedTranscript", [])
            ],
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)

    if status == "failed":
        return json.dumps({
            "job_id": job_id,
            "status": "failed",
            "error": data.get("error", {}),
        })

    # Still processing
    return json.dumps({
        "job_id": job_id,
        "status": status,
        "message": "Job still processing. Poll again in a few seconds.",
    })


@mcp.tool()
def create_api_key(name: str = "", tier: str = "free") -> str:
    """Create a new API key for the KeyFrame Transcription API.

    Tiers: free (5/month), starter ($0.10/video), pro ($0.08/video), enterprise ($0.06/video).
    The full API key is returned only once — store it securely.

    Args:
        name: Human-readable label for the key
        tier: Pricing tier (free, starter, pro, enterprise)
    """
    import requests as http_requests

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v1/keys",
        json={"name": name, "tier": tier},
        headers=_headers(),
        timeout=10,
    )

    if resp.status_code != 200:
        return f"Error: Failed to create key: {resp.text[:200]}"

    data = resp.json()
    return json.dumps({
        "api_key": data["key"],
        "key_id": data["key_id"],
        "tier": data["tier"],
        "monthly_quota": data["monthly_quota"],
        "rate_limit_rpm": data["rate_limit_rpm"],
        "warning": "Store the api_key securely — it will not be shown again.",
    })


@mcp.tool()
def check_usage() -> str:
    """Check your current API usage, remaining quota, and estimated cost.

    Requires KEYFRAME_API_KEY environment variable to be set.
    """
    import requests as http_requests

    if not API_KEY:
        return "Error: Set KEYFRAME_API_KEY environment variable first."

    resp = http_requests.get(
        f"{API_BASE_URL}/api/v1/usage",
        headers=_headers(),
        timeout=10,
    )

    if resp.status_code != 200:
        return f"Error: Failed to get usage: {resp.text[:200]}"

    data = resp.json()
    return json.dumps(data, indent=2)


@mcp.tool()
def health_check() -> str:
    """Check if the KeyFrame Transcription API is healthy and available.

    Use this before submitting transcription jobs to verify the service is running.
    """
    import requests as http_requests

    try:
        resp = http_requests.get(f"{API_BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return f"Service is healthy. Version: {data.get('version', 'unknown')}. Uptime: {data.get('uptime_s', 0):.0f}s"
        return f"Service returned {resp.status_code}"
    except Exception as e:
        return f"Service unreachable: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
