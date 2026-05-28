FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies in layers for faster rebuilds
# Heavy packages first (PyTorch ~2GB) — this layer caches
COPY requirements.txt .
RUN pip install --no-cache-dir torch && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY transcribe.py schemas.py config.py rate_limiter.py mcp_server.py sdk.py cli.py run.py ./

# Create cache directory
RUN mkdir -p cache/transcripts

# Render assigns PORT dynamically; default to 8000 for local dev
ENV PORT=8000
EXPOSE $PORT

# Run with uvicorn using the PORT env var
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
