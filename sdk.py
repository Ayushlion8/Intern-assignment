"""Auto-generated Python SDK client for the KeyFrame Transcription API.

This client can be used directly by AI agents or developers to interact
with the transcription API without constructing raw HTTP requests.

Usage:
    from sdk import KeyFrameClient

    client = KeyFrameClient(api_key="kf_...")
    job = client.transcribe("https://example.com/video.mp4")
    result = client.wait_for_result(job["job_id"])
    print(result["text"])

Or with an API base URL:
    client = KeyFrameClient(api_key="kf_...", base_url="https://api.keyframe.ink")
"""

from __future__ import annotations

import time
from typing import Any

import requests


class KeyFrameError(Exception):
    """Error from the KeyFrame API with machine-readable context."""

    def __init__(self, code: str, message: str, action: str, doc_url: str | None = None):
        self.code = code
        self.message = message
        self.action = action
        self.doc_url = doc_url
        super().__init__(f"[{code}] {message} (action: {action})")


class KeyFrameClient:
    """Python SDK client for the KeyFrame Transcription API.

    Args:
        api_key: API key for authentication (starts with 'kf_')
        base_url: API base URL (default: http://localhost:8000)
    """

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, json_body: dict | None = None, timeout: int = 30) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, json=json_body, timeout=timeout)

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", {}).get("error", {})
            except Exception:
                detail = {}
            raise KeyFrameError(
                code=detail.get("code", f"HTTP_{resp.status_code}"),
                message=detail.get("message", resp.text[:200]),
                action=detail.get("action", "retry"),
                doc_url=detail.get("doc_url"),
            )

        return resp.json()

    # --- Health ---

    def health(self) -> dict[str, Any]:
        """Check if the API service is healthy.

        Returns:
            dict with status, version, uptime_s
        """
        resp = self._session.get(f"{self.base_url}/health", timeout=5)
        return resp.json()

    # --- API Key Management ---

    @staticmethod
    def create_key(name: str = "", tier: str = "free",
                   base_url: str = "http://localhost:8000") -> dict[str, Any]:
        """Create a new API key (no auth required).

        Args:
            name: Human-readable label
            tier: free | starter | pro | enterprise
            base_url: API base URL

        Returns:
            dict with key, key_id, tier, monthly_quota, rate_limit_rpm
        """
        resp = requests.post(
            f"{base_url}/api/v1/keys",
            json={"name": name, "tier": tier},
            timeout=10,
        )
        return resp.json()

    # --- Transcription ---

    def transcribe(self, url: str, model: str | None = None) -> dict[str, Any]:
        """Submit a video/audio URL for transcription.

        Args:
            url: Public URL to a video or audio file
            model: Optional — force a specific Gemini model

        Returns:
            dict with job_id, status, poll_url

        Raises:
            KeyFrameError: On auth, rate limit, or quota errors
        """
        body = {"url": url}
        if model:
            body["model"] = model
        return self._request("POST", "/api/v1/transcribe", body)

    def transcribe_file(self, file_path: str, model: str | None = None) -> dict[str, Any]:
        """Upload a local video/audio file for transcription.

        Args:
            file_path: Path to a local video or audio file (max 100 MB)
            model: Optional — force a specific Gemini model

        Returns:
            dict with job_id, status, poll_url
        """
        import mimetypes
        mime = mimetypes.guess_type(file_path)[0] or "video/mp4"
        with open(file_path, "rb") as f:
            resp = self._session.post(
                f"{self.base_url}/api/v1/transcribe/upload",
                files={"file": (file_path, f, mime)},
                data={"model": model or ""},
                timeout=120,
            )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", {}).get("error", {})
            except Exception:
                detail = {}
            raise KeyFrameError(
                code=detail.get("code", f"HTTP_{resp.status_code}"),
                message=detail.get("message", resp.text[:200]),
                action=detail.get("action", "retry"),
                doc_url=detail.get("doc_url"),
            )
        return resp.json()

    # --- Job Status ---

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Get job status and result.

        Args:
            job_id: Job identifier from transcribe()

        Returns:
            dict with job_id, status, created_at, completed_at, result, error
        """
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def wait_for_result(self, job_id: str, timeout: int = 300,
                        poll_interval: int = 3) -> dict[str, Any]:
        """Poll job status until completed or failed.

        Args:
            job_id: Job identifier
            timeout: Max seconds to wait (default 5 minutes)
            poll_interval: Seconds between polls

        Returns:
            TranscriptionResult dict when completed

        Raises:
            KeyFrameError: If the job fails
            TimeoutError: If timeout is exceeded
        """
        start = time.time()
        while time.time() - start < timeout:
            job = self.get_job(job_id)
            if job["status"] == "completed":
                return job["result"]
            if job["status"] == "failed":
                err = job.get("error", {})
                raise KeyFrameError(
                    code=err.get("code", "JOB_FAILED"),
                    message=err.get("message", "Transcription failed"),
                    action=err.get("action", "retry"),
                    doc_url=err.get("doc_url"),
                )
            time.sleep(poll_interval)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    # --- Usage ---

    def usage(self) -> dict[str, Any]:
        """Get usage stats and remaining quota.

        Returns:
            dict with key_id, tier, usage_month, usage_count, monthly_quota, remaining, cost_usd
        """
        return self._request("GET", "/api/v1/usage")


# ---------------------------------------------------------------------------
# Convenience: run from command line
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KeyFrame Transcription API SDK")
    parser.add_argument("--api-key", required=True, help="API key")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    sub = parser.add_subparsers(dest="cmd")

    # transcribe
    t = sub.add_parser("transcribe", help="Submit a transcription job")
    t.add_argument("url", help="Media URL")
    t.add_argument("--model", default=None)

    # result
    r = sub.add_parser("result", help="Wait for transcription result")
    r.add_argument("job_id", help="Job ID")

    # usage
    sub.add_parser("usage", help="Check usage")

    # health
    sub.add_parser("health", help="Health check")

    args = parser.parse_args()
    client = KeyFrameClient(api_key=args.api_key, base_url=args.base_url)

    if args.cmd == "transcribe":
        job = client.transcribe(args.url, model=args.model)
        print(f"Job submitted: {job['job_id']} (status: {job['status']})")
    elif args.cmd == "result":
        result = client.wait_for_result(args.job_id)
        print(f"Language: {result.get('detectedLanguage', '?')}")
        print(f"Audio: {result.get('audioMode', '?')}")
        print(f"Text: {result.get('text', '')}")
    elif args.cmd == "usage":
        print(client.usage())
    elif args.cmd == "health":
        print(client.health())
    else:
        parser.print_help()
