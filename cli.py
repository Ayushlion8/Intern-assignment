"""CLI tool for managing API keys.

Usage:
    python cli.py keys create [--name NAME] [--tier TIER]
    python cli.py keys list
    python cli.py keys revoke KEY_ID
    python cli.py keys usage KEY_ID
    python cli.py health
    python cli.py transcribe URL [--model MODEL]
    python cli.py jobs JOB_ID
"""

from __future__ import annotations

import argparse
import json
import sys

API_BASE = "http://localhost:8000"


def _make_request(method: str, path: str, api_key: str = "", body: dict | None = None) -> dict | None:
    import requests
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=body, headers=headers, timeout=10)
        else:
            print(f"Unknown method: {method}")
            return None
        if resp.status_code >= 400:
            err = resp.json().get("detail", {}).get("error", {})
            print(f"Error ({resp.status_code}): {err.get('code', 'UNKNOWN')} — {err.get('message', resp.text[:200])}")
            return None
        return resp.json()
    except Exception as e:
        print(f"Request failed: {e}")
        return None


def cmd_keys_create(args):
    from app.auth import create_key
    result = create_key(name=args.name, tier=args.tier)
    print(f"API Key created successfully!")
    print(f"  Key:      {result.key}")
    print(f"  Key ID:   {result.key_id}")
    print(f"  Tier:     {result.tier}")
    print(f"  Quota:    {result.monthly_quota}/month")
    print(f"  Rate:     {result.rate_limit_rpm} RPM")
    print()
    print("IMPORTANT: Store the key securely — it won't be shown again.")


def cmd_keys_list(args):
    from app.auth import list_keys
    keys = list_keys()
    if not keys:
        print("No API keys found.")
        return
    print(f"{'Key ID':<10} {'Name':<20} {'Tier':<12} {'Usage':<10} {'Quota':<10} {'Enabled'}")
    print("-" * 75)
    for k in keys:
        quota_str = str(k["monthly_quota"]) if k["monthly_quota"] != -1 else "Unlimited"
        print(f"{k['key_id']:<10} {k['name']:<20} {k['tier']:<12} {k['usage_count']:<10} {quota_str:<10} {k['enabled']}")


def cmd_keys_revoke(args):
    from app.auth import _load_keys, _save_keys, _lock
    with _lock:
        keys = _load_keys()
        if args.key_id not in keys:
            print(f"Key {args.key_id} not found.")
            return
        keys[args.key_id].enabled = False
        _save_keys(keys)
    print(f"Key {args.key_id} has been revoked.")


def cmd_keys_usage(args):
    from app.auth import get_usage
    usage = get_usage(args.key_id)
    if usage is None:
        print(f"Key {args.key_id} not found.")
        return
    print(f"Usage for {usage.key_id}:")
    print(f"  Tier:       {usage.tier}")
    print(f"  Month:      {usage.usage_month}")
    print(f"  Used:       {usage.usage_count}")
    print(f"  Remaining:  {usage.remaining}" + ("" if usage.remaining >= 0 else " (unlimited)"))
    print(f"  Cost:       ${usage.cost_usd:.2f}")


def cmd_health(args):
    import requests
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        data = resp.json()
        print(f"Status:  {data['status']}")
        print(f"Version: {data['version']}")
        print(f"Uptime:  {data['uptime_s']:.0f}s")
    except Exception as e:
        print(f"Service unreachable: {e}")


def cmd_transcribe(args):
    api_key = args.api_key
    if not api_key:
        print("Error: --api-key is required. Set KEYFRAME_API_KEY or pass --api-key.")
        return
    data = _make_request("POST", "/api/v1/transcribe", api_key, {"url": args.url, "model": args.model})
    if data:
        print(f"Job submitted: {data['job_id']}")
        print(f"Status: {data['status']}")
        print(f"Poll:   GET {API_BASE}{data['poll_url']}")


def cmd_jobs(args):
    api_key = args.api_key
    if not api_key:
        print("Error: --api-key is required.")
        return
    data = _make_request("GET", f"/api/v1/jobs/{args.job_id}", api_key)
    if data:
        print(f"Job:     {data['job_id']}")
        print(f"Status:  {data['status']}")
        if data.get("result"):
            result = data["result"]
            print(f"Language: {result.get('detectedLanguage', '?')} ({result.get('detectedLanguageName', '')})")
            print(f"Audio:    {result.get('audioMode', '?')}")
            print(f"Text:     {result.get('text', '')[:200]}")
            for seg in result.get("diarizedTranscript", []):
                print(f"  [{seg.get('speaker', '?')}] ({seg.get('language', '?')}) {seg.get('text', '')}")
        elif data.get("error"):
            err = data["error"]
            print(f"Error: {err.get('code', '?')} — {err.get('message', '')}")
            if err.get("action"):
                print(f"Action: {err['action']}")


def main():
    parser = argparse.ArgumentParser(
        prog="keyframe",
        description="KeyFrame Transcription API CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    # keys
    keys_parser = subparsers.add_parser("keys", help="Manage API keys")
    keys_sub = keys_parser.add_subparsers(dest="keys_command")

    # keys create
    create_p = keys_sub.add_parser("create", help="Create a new API key")
    create_p.add_argument("--name", default="", help="Human-readable key label")
    create_p.add_argument("--tier", default="free", choices=["free", "starter", "pro", "enterprise"], help="Pricing tier")

    # keys list
    keys_sub.add_parser("list", help="List all API keys")

    # keys revoke
    revoke_p = keys_sub.add_parser("revoke", help="Revoke an API key")
    revoke_p.add_argument("key_id", help="Key ID to revoke")

    # keys usage
    usage_p = keys_sub.add_parser("usage", help="Check usage for an API key")
    usage_p.add_argument("key_id", help="Key ID to check")

    # health
    subparsers.add_parser("health", help="Check API health")

    # transcribe
    trans_p = subparsers.add_parser("transcribe", help="Submit a transcription job")
    trans_p.add_argument("url", help="URL to video/audio file")
    trans_p.add_argument("--model", default=None, help="Force Gemini model")
    trans_p.add_argument("--api-key", default=None, help="API key (or set KEYFRAME_API_KEY env var)")

    # jobs
    jobs_p = subparsers.add_parser("jobs", help="Check job status")
    jobs_p.add_argument("job_id", help="Job ID to check")
    jobs_p.add_argument("--api-key", default=None, help="API key")

    args = parser.parse_args()

    # Fallback to env var for api key
    if hasattr(args, "api_key") and not args.api_key:
        import os
        args.api_key = os.getenv("KEYFRAME_API_KEY", "")

    commands = {
        ("keys", "create"): cmd_keys_create,
        ("keys", "list"): cmd_keys_list,
        ("keys", "revoke"): cmd_keys_revoke,
        ("keys", "usage"): cmd_keys_usage,
        ("health",): cmd_health,
        ("transcribe",): cmd_transcribe,
        ("jobs",): cmd_jobs,
    }

    key = (args.command,) + ((args.keys_command,) if hasattr(args, "keys_command") else ())
    handler = commands.get(key)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
