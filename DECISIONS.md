# Design Decisions

## API Pattern: Polling over Webhooks/SSE

**Decision**: Use a polling pattern (submit → get job_id → poll status → get result).

**Rationale**: The pipeline takes 10–60 seconds. Options considered:
- **Synchronous HTTP**: Blocks the connection for up to 60s — bad for load balancers, clients, and timeouts.
- **Server-Sent Events (SSE)**: Requires keeping the connection open; many agents/HTTP clients don't handle SSE well.
- **Webhooks**: Requires the caller to expose an HTTP endpoint; adds complexity for agent consumers.
- **Polling**: Simple, universally supported, agent-friendly. The job_id pattern is familiar (S3, GCS, AssemblyAI all use it). Agents can implement a simple retry loop.

Polling wins because every HTTP client supports it and it requires zero infrastructure on the agent side.

## Framework: FastAPI

**Decision**: FastAPI over Flask or Django.

**Rationale**:
- Auto-generates OpenAPI spec from type annotations (critical for agent discoverability).
- Native async support for file uploads.
- Pydantic integration matches the existing schema models.
- Widely adopted, good docs.

## Job Storage: In-Memory with Thread Safety

**Decision**: In-memory dict with threading locks, not a database.

**Rationale**: For a single-instance deployment, an in-memory store is sufficient. Adding Redis or SQLite would be over-engineering for the assessment scope. The job manager uses `threading.Lock` for safety and `threading.Semaphore` for concurrency control (max 4 concurrent transcriptions). If this needed to scale, the interface is simple enough to swap in Redis.

## API Key Storage: JSON File

**Decision**: Store API keys in a local JSON file (`api_keys.json`).

**Rationale**: Only the SHA-256 hash of the key is stored (never the plaintext). The raw key is returned once at creation time. A JSON file is sufficient for single-instance deployments and persists across restarts without requiring a database.

## Authentication: Header-Based API Key

**Decision**: `X-API-Key` header, not Bearer token or query param.

**Rationale**: Simple, explicit, and widely supported. Bearer tokens imply OAuth2 complexity we don't need. Query params leak keys into logs and URLs. `X-API-Key` is clear and agent-friendly.

## Rate Limiting: Sliding Window Per-Key

**Decision**: In-memory sliding window counter per API key.

**Rationale**: The existing `rate_limiter.py` is a token bucket for upstream service calls (Gemini, Chirp 3). For the API-facing rate limiter, a sliding window is simpler to reason about and provides more predictable behavior. Per-key limits prevent a single user from consuming all capacity.

## Pricing Model

**Decision**:
| Tier | Monthly Quota | Price/Video | RPM |
|------|--------------|-------------|-----|
| Free | 5 | $0.00 | 5 |
| Starter | 100 | $0.10 | 30 |
| Pro | 1,000 | $0.08 | 60 |
| Enterprise | Unlimited | $0.06 | 120 |

**Rationale**: Pipeline cost is $0.02–0.08 per video. Pricing at $0.10/video (starter) gives 25–400% margin. The free tier (5/month) lets agents test the API with zero commitment. Pricing aligns with competitors:
- Deepgram: $0.0125/min (pay-as-you-go)
- AssemblyAI: $0.00013/s ($0.65 for 50min) with diarization add-on
- Google STT: $0.016/min standard, $0.024/min enhanced

Our pricing is higher per-video but includes diarization + translation + structured output, which competitors charge extra for.

## Error Design: Machine-Readable Errors

**Decision**: Every error response includes `code`, `message`, `action`, and `doc_url`.

**Rationale**: Agents need to programmatically decide whether to retry, change input, or escalate. A human-readable message alone doesn't help. The `action` field tells the agent exactly what to do (`retry`, `reduce_file_size`, `check_auth`, `wait_and_retry`, `upgrade_plan`, `contact_support`). The `doc_url` links to specific error documentation.

## Agent Discoverability: Multiple Standards

**Decision**: Implement llms.txt, /.well-known/ai-plugin.json, /.well-known/mcp, and full OpenAPI spec.

**Rationale**: There's no single standard for agent discoverability yet. By implementing multiple:
- **llms.txt**: Emerging standard for AI agents (proposed by The Guardian/other publishers).
- **OpenAPI**: The gold standard for API description; FastAPI auto-generates it.
- **AI Plugin Manifest**: OpenAI's plugin standard; some agents use this.
- **MCP info endpoint**: Describes the MCP server for tool integration.
- **MCP server**: Actual runnable MCP server that agents can connect to.

An agent reading *any* one of these should be able to understand and use the API.

## MCP Server: Standalone Script

**Decision**: The MCP server is a standalone script that calls the HTTP API, not an in-process tool.

**Rationale**: MCP servers are meant to be run as separate processes communicating over stdio. By calling the HTTP API, the MCP server works with any deployment (local, cloud) and inherits all the auth/rate-limiting/error-handling of the main API.

## Deployment

**Decision**: Designed for Railway/Render deployment with Uvicorn.

**Rationale**: The pipeline needs ffmpeg and ~2GB for PyTorch/Whisper. Railway and Render both support Docker deployments with these requirements. The `Dockerfile` and `railway.json` (or `render.yaml`) make deployment a single command.

## Assumptions

1. **Single-instance deployment**: The job store is in-memory; horizontal scaling would require external storage (Redis).
2. **Short-form video**: The pipeline is optimized for videos under ~5 minutes. Very long videos may time out.
3. **GCP credentials**: The user provides their own GCP service account. The service doesn't manage GCP auth on behalf of users.
4. **No persistent billing**: Usage tracking is monthly in-memory. For production, integrate Stripe or similar.
5. **Free-tier key creation is unauthenticated**: Anyone can create a free-tier API key. For production, add email verification or admin approval.
