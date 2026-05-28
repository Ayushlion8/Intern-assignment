"""Tests for the KeyFrame Transcription API."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.auth import create_key, validate_key, get_usage, TIERS


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    """Create a free-tier API key for testing."""
    result = create_key(name="test-key", tier="free")
    return result.key


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert "uptime_s" in data


class TestAPIKeyManagement:
    def test_create_key_default_tier(self, client):
        resp = client.post("/api/v1/keys", json={"name": "test", "tier": "free"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"].startswith("kf_")
        assert data["tier"] == "free"
        assert data["monthly_quota"] == 5
        assert data["rate_limit_rpm"] == 5

    def test_create_key_starter_tier(self, client):
        resp = client.post("/api/v1/keys", json={"name": "paid", "tier": "starter"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "starter"
        assert data["monthly_quota"] == 100

    def test_create_key_invalid_tier(self, client):
        resp = client.post("/api/v1/keys", json={"name": "bad", "tier": "platinum"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["error"]["code"] == "INVALID_INPUT"

    def test_validate_key_format(self):
        result = create_key(name="validation-test", tier="free")
        raw_key = result.key
        info = validate_key(raw_key)
        assert info is not None
        assert info.tier == "free"
        assert info.name == "validation-test"

    def test_validate_invalid_key(self):
        info = validate_key("kf_invalid_key")
        assert info is None

    def test_validate_empty_key(self):
        info = validate_key("")
        assert info is None


class TestAuth:
    def test_transcribe_without_api_key(self, client):
        resp = client.post("/api/v1/transcribe", json={"url": "https://example.com/v.mp4"})
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"]["error"]["code"] == "AUTH_MISSING"

    def test_transcribe_with_invalid_api_key(self, client):
        resp = client.post(
            "/api/v1/transcribe",
            json={"url": "https://example.com/v.mp4"},
            headers={"X-API-Key": "kf_invalid"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"]["error"]["code"] == "AUTH_INVALID"


class TestTranscribeURL:
    def test_submit_url_returns_job(self, client, api_key):
        resp = client.post(
            "/api/v1/transcribe",
            json={"url": "https://example.com/video.mp4"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] in ("queued", "processing")
        assert "/api/v1/jobs/" in data["poll_url"]

    def test_get_job_status(self, client, api_key):
        # Submit a job
        submit_resp = client.post(
            "/api/v1/transcribe",
            json={"url": "https://example.com/video.mp4"},
            headers={"X-API-Key": api_key},
        )
        job_id = submit_resp.json()["job_id"]

        # Poll for status
        status_resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"X-API-Key": api_key},
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("queued", "processing", "completed", "failed")

    def test_get_nonexistent_job(self, client, api_key):
        resp = client.get(
            "/api/v1/jobs/nonexistent",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "JOB_NOT_FOUND"


class TestUsage:
    def test_get_usage(self, client, api_key):
        resp = client.get(
            "/api/v1/usage",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert data["monthly_quota"] == 5
        assert data["remaining"] == 5
        assert data["usage_count"] == 0

    def test_get_usage_without_auth(self, client):
        resp = client.get("/api/v1/usage")
        assert resp.status_code == 401


class TestAgentDiscoverability:
    def test_llms_txt(self, client):
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        text = resp.text
        assert "KeyFrame" in text
        assert "/api/v1/transcribe" in text
        assert "Authentication" in text

    def test_llms_full_txt(self, client):
        resp = client.get("/llms-full.txt")
        assert resp.status_code == 200
        assert "KeyFrame" in resp.text

    def test_openapi_spec(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["info"]["title"] == "KeyFrame Transcription API"
        assert "/api/v1/transcribe" in spec["paths"]

    def test_ai_plugin_manifest(self, client):
        resp = client.get("/.well-known/ai-plugin.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name_for_model"] == "keyframe_transcription"
        assert "openapi" in data["api"]["type"]

    def test_mcp_info(self, client):
        resp = client.get("/.well-known/mcp")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "keyframe-transcription"
        assert len(data["tools"]) >= 2


class TestErrorResponses:
    def test_error_has_machine_readable_code(self, client):
        resp = client.post("/api/v1/transcribe", json={"url": "https://example.com/v.mp4"})
        assert resp.status_code == 401
        data = resp.json()
        error = data["detail"]["error"]
        assert "code" in error
        assert "message" in error
        assert "action" in error
        # Action should be a valid suggestion
        assert error["action"] in ("retry", "reduce_file_size", "check_auth", "wait_and_retry", "contact_support", "upgrade_plan")

    def test_file_too_large_error(self, client, api_key):
        # We can't easily test a 100MB upload in unit tests,
        # but we can verify the error response structure
        from app.errors import file_too_large
        err = file_too_large(150.0)
        assert err.error.code == "FILE_TOO_LARGE"
        assert err.error.action == "reduce_file_size"
        assert err.error.doc_url is not None


class TestPricing:
    def test_tiers_defined(self):
        assert "free" in TIERS
        assert "starter" in TIERS
        assert "pro" in TIERS
        assert "enterprise" in TIERS

    def test_free_tier_values(self):
        assert TIERS["free"]["monthly_quota"] == 5
        assert TIERS["free"]["price_per_video"] == 0.0

    def test_enterprise_unlimited(self):
        assert TIERS["enterprise"]["monthly_quota"] == -1


class TestSDK:
    def test_sdk_import(self):
        from sdk import KeyFrameClient, KeyFrameError
        assert KeyFrameClient is not None
        assert KeyFrameError is not None

    def test_sdk_error_format(self):
        from sdk import KeyFrameError
        err = KeyFrameError(code="TEST", message="test error", action="retry")
        assert "[TEST]" in str(err)
        assert err.code == "TEST"
        assert err.action == "retry"


class TestCLI:
    def test_cli_import(self):
        import cli
        assert hasattr(cli, "main")

    def test_cli_keys_create(self):
        from app.auth import create_key
        result = create_key(name="cli-test", tier="free")
        assert result.key.startswith("kf_")
        assert result.tier == "free"


class TestLlmsFullTxt:
    def test_llms_full_txt_is_richer(self, client):
        resp = client.get("/llms-full.txt")
        assert resp.status_code == 200
        text = resp.text
        # Should have much more detail than llms.txt
        assert "DiarizedSegment" in text
        assert "POST /api/v1/keys" in text
        assert "sdk.py" in text or "SDK" in text
        assert "cli.py" in text or "CLI" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
