"""Agent-optimized error response models.

Errors include machine-readable codes, suggested actions, and doc links
so AI agents can programmatically decide whether to retry, escalate, or adjust.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """A single error with machine-readable context for agents."""

    code: str = Field(
        ...,
        description="Machine-readable error code, e.g. 'FILE_TOO_LARGE', 'UPSTREAM_TIMEOUT'",
        examples=["FILE_TOO_LARGE"],
    )
    message: str = Field(
        ...,
        description="Human-readable description of what went wrong",
        examples=["Uploaded file exceeds the 100 MB limit"],
    )
    action: Literal["retry", "reduce_file_size", "check_auth", "wait_and_retry", "contact_support", "upgrade_plan"] = Field(
        ...,
        description="Suggested action the caller should take",
        examples=["reduce_file_size"],
    )
    doc_url: str | None = Field(
        None,
        description="Link to relevant documentation",
        examples=["https://docs.keyframe.ink/errors#FILE_TOO_LARGE"],
    )


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all failing endpoints."""

    error: ErrorDetail
    request_id: str | None = Field(
        None,
        description="Unique request identifier for debugging",
    )


# --- Pre-built error helpers ---

DOC_BASE = "https://docs.keyframe.ink/errors"


def _err(code: str, message: str, action: str, doc_slug: str | None = None) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            action=action,
            doc_url=f"{DOC_BASE}#{doc_slug}" if doc_slug else None,
        ),
    )


def auth_missing() -> ErrorResponse:
    return _err("AUTH_MISSING", "Missing or invalid API key in X-API-Key header", "check_auth", "AUTH_MISSING")


def auth_invalid() -> ErrorResponse:
    return _err("AUTH_INVALID", "The provided API key is not recognized or has been revoked", "check_auth", "AUTH_INVALID")


def file_too_large(size_mb: float, limit_mb: int = 100) -> ErrorResponse:
    return _err("FILE_TOO_LARGE", f"Uploaded file is {size_mb:.1f} MB, exceeds {limit_mb} MB limit", "reduce_file_size", "FILE_TOO_LARGE")


def upstream_timeout(service: str) -> ErrorResponse:
    return _err("UPSTREAM_TIMEOUT", f"Upstream service {service} timed out; transcription may still complete", "wait_and_retry", "UPSTREAM_TIMEOUT")


def upstream_error(service: str, detail: str = "") -> ErrorResponse:
    msg = f"Upstream service {service} returned an error"
    if detail:
        msg += f": {detail}"
    return _err("UPSTREAM_ERROR", msg, "retry", "UPSTREAM_ERROR")


def rate_limited(retry_after_s: int) -> ErrorResponse:
    resp = _err("RATE_LIMITED", f"Rate limit exceeded; retry after {retry_after_s}s", "wait_and_retry", "RATE_LIMITED")
    return resp


def quota_exceeded(remaining: int = 0) -> ErrorResponse:
    return _err("QUOTA_EXCEEDED", f"Monthly quota exceeded ({remaining} remaining)", "upgrade_plan", "QUOTA_EXCEEDED")


def job_not_found(job_id: str) -> ErrorResponse:
    return _err("JOB_NOT_FOUND", f"Job {job_id} not found", "check_auth", "JOB_NOT_FOUND")


def invalid_input(message: str) -> ErrorResponse:
    return _err("INVALID_INPUT", message, "retry", "INVALID_INPUT")


def unsupported_media_type(mime: str) -> ErrorResponse:
    return _err("UNSUPPORTED_MEDIA_TYPE", f"Media type '{mime}' is not supported; use audio/* or video/*", "retry", "UNSUPPORTED_MEDIA_TYPE")


def internal_error(request_id: str | None = None) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred",
            action="contact_support",
            doc_url=f"{DOC_BASE}#INTERNAL_ERROR",
        ),
        request_id=request_id,
    )
