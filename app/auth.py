"""API key management — generation, validation, persistence.

Keys are stored in a simple JSON file (api_keys.json) for persistence
across restarts. For a single-instance deployment this is sufficient.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# Pricing tiers
TIERS = {
    "free": {"monthly_quota": 5, "price_per_video": 0.0, "rate_limit_rpm": 5},
    "starter": {"monthly_quota": 100, "price_per_video": 0.10, "rate_limit_rpm": 30},
    "pro": {"monthly_quota": 1000, "price_per_video": 0.08, "rate_limit_rpm": 60},
    "enterprise": {"monthly_quota": -1, "price_per_video": 0.06, "rate_limit_rpm": 120},
}


class APIKeyInfo(BaseModel):
    """Metadata stored alongside each API key."""
    key_hash: str = Field(description="SHA-256 hash of the raw key (we never store plaintext)")
    name: str = Field(default="", description="Human-readable label for this key")
    tier: str = Field(default="free", description="Pricing tier: free | starter | pro | enterprise")
    created_at: float = Field(description="Unix timestamp of key creation")
    enabled: bool = Field(default=True, description="Whether the key is active")
    usage_month: str = Field(default="", description="Current billing month in YYYY-MM format")
    usage_count: int = Field(default=0, description="Number of videos transcribed this month")


class APIKeyResponse(BaseModel):
    """Returned once when a key is created — the only time the raw key is visible."""
    key: str = Field(description="Full API key (store this — it won't be shown again)")
    key_id: str = Field(description="Short public identifier derived from the key hash")
    name: str = Field(description="Human-readable label")
    tier: str = Field(description="Assigned pricing tier")
    monthly_quota: int = Field(description="Max transcriptions per month (-1 = unlimited)")
    rate_limit_rpm: int = Field(description="Max requests per minute")


class UsageResponse(BaseModel):
    """Usage stats for the authenticated API key."""
    key_id: str = Field(description="Short public key identifier")
    tier: str = Field(description="Current pricing tier")
    usage_month: str = Field(description="Billing month")
    usage_count: int = Field(description="Videos transcribed this month")
    monthly_quota: int = Field(description="Monthly limit (-1 = unlimited)")
    remaining: int = Field(description="Remaining transcriptions this month (-1 = unlimited)")
    cost_usd: float = Field(description="Estimated cost incurred this month")


# ---------------------------------------------------------------------------
# Key storage
# ---------------------------------------------------------------------------

_KEYS_FILE = Path(os.getenv("API_KEYS_FILE", "api_keys.json"))
_lock = threading.Lock()


def _load_keys() -> dict[str, APIKeyInfo]:
    """Load keys from disk. Returns dict keyed by key_id."""
    if not _KEYS_FILE.exists():
        return {}
    try:
        raw = json.loads(_KEYS_FILE.read_text())
        return {kid: APIKeyInfo(**v) for kid, v in raw.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


def _save_keys(keys: dict[str, APIKeyInfo]) -> None:
    """Persist keys to disk."""
    data = {kid: v.model_dump() for kid, v in keys.items()}
    _KEYS_FILE.write_text(json.dumps(data, indent=2))


def _derive_key_id(key_hash: str) -> str:
    """Short public identifier from the hash (first 8 chars)."""
    return key_hash[:8]


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of the raw key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------

def create_key(name: str = "", tier: str = "free") -> APIKeyResponse:
    """Generate a new API key and persist it. Returns the full key once."""
    raw_key = f"kf_{secrets.token_hex(24)}"
    key_hash = _hash_key(raw_key)
    key_id = _derive_key_id(key_hash)

    now = time.time()
    month_str = time.strftime("%Y-%m", time.gmtime(now))

    info = APIKeyInfo(
        key_hash=key_hash,
        name=name or f"key-{key_id}",
        tier=tier,
        created_at=now,
        usage_month=month_str,
    )

    with _lock:
        keys = _load_keys()
        keys[key_id] = info
        _save_keys(keys)

    tier_info = TIERS.get(tier, TIERS["free"])
    return APIKeyResponse(
        key=raw_key,
        key_id=key_id,
        name=info.name,
        tier=tier,
        monthly_quota=tier_info["monthly_quota"],
        rate_limit_rpm=tier_info["rate_limit_rpm"],
    )


def validate_key(raw_key: str) -> APIKeyInfo | None:
    """Validate a raw API key. Returns key info if valid, None otherwise."""
    if not raw_key or not raw_key.startswith("kf_"):
        return None

    key_hash = _hash_key(raw_key)
    key_id = _derive_key_id(key_hash)

    with _lock:
        keys = _load_keys()
        info = keys.get(key_id)
        if info is None:
            return None
        if not info.enabled:
            return None
        if info.key_hash != key_hash:
            return None

    # Reset monthly counter if we're in a new month
    month_str = time.strftime("%Y-%m", time.gmtime())
    if info.usage_month != month_str:
        with _lock:
            keys = _load_keys()
            if key_id in keys:
                keys[key_id].usage_month = month_str
                keys[key_id].usage_count = 0
                _save_keys(keys)
        info.usage_month = month_str
        info.usage_count = 0

    return info


def increment_usage(key_id: str) -> None:
    """Increment usage counter for the given key."""
    month_str = time.strftime("%Y-%m", time.gmtime())
    with _lock:
        keys = _load_keys()
        if key_id in keys:
            info = keys[key_id]
            if info.usage_month != month_str:
                info.usage_month = month_str
                info.usage_count = 0
            info.usage_count += 1
            _save_keys(keys)


def get_usage(key_id: str) -> UsageResponse | None:
    """Get usage stats for the given key."""
    with _lock:
        keys = _load_keys()
        info = keys.get(key_id)
        if info is None:
            return None

    tier_info = TIERS.get(info.tier, TIERS["free"])
    quota = tier_info["monthly_quota"]
    remaining = -1 if quota == -1 else max(0, quota - info.usage_count)
    cost = info.usage_count * tier_info["price_per_video"]

    return UsageResponse(
        key_id=key_id,
        tier=info.tier,
        usage_month=info.usage_month,
        usage_count=info.usage_count,
        monthly_quota=quota,
        remaining=remaining,
        cost_usd=round(cost, 2),
    )


def list_keys() -> list[dict[str, Any]]:
    """List all keys (for admin purposes)."""
    with _lock:
        keys = _load_keys()
    result = []
    for kid, info in keys.items():
        tier_info = TIERS.get(info.tier, TIERS["free"])
        result.append({
            "key_id": kid,
            "name": info.name,
            "tier": info.tier,
            "enabled": info.enabled,
            "created_at": info.created_at,
            "usage_count": info.usage_count,
            "monthly_quota": tier_info["monthly_quota"],
        })
    return result
