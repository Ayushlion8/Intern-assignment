"""Background job manager for async transcription.

Uses an in-memory job store with thread-safe access.
Jobs are processed in a background thread pool.
"""

from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.auth import get_usage, increment_usage


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    key_id: str = ""
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    input_type: str = ""  # "upload" or "url"
    input_name: str = ""  # filename or URL
    file_path: str | None = None  # temp file path (cleaned up after processing)


class JobManager:
    """Thread-safe in-memory job store with background processing."""

    def __init__(self, max_workers: int = 4):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_workers)
        self._threads: list[threading.Thread] = []

    def create_job(self, key_id: str, input_type: str, input_name: str,
                   file_path: str | None = None, url: str | None = None,
                   model: str | None = None) -> Job:
        """Create a new job and start background processing."""
        job_id = uuid.uuid4().hex[:12]

        # Check quota before creating
        usage = get_usage(key_id)
        if usage and usage.monthly_quota != -1 and usage.remaining <= 0:
            raise QuotaExceededError(usage.remaining)

        job = Job(
            job_id=job_id,
            key_id=key_id,
            input_type=input_type,
            input_name=input_name,
            file_path=file_path,
        )

        with self._lock:
            self._jobs[job_id] = job

        # Start processing in background thread
        t = threading.Thread(
            target=self._process_job,
            args=(job_id, url, model),
            daemon=True,
        )
        t.start()
        self._threads.append(t)

        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, key_id: str | None = None) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        if key_id:
            jobs = [j for j in jobs if j.key_id == key_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def _update_job(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)
                job.updated_at = time.time()

    def _process_job(self, job_id: str, url: str | None, model: str | None) -> None:
        """Run transcription in a background thread."""
        with self._semaphore:
            self._update_job(job_id, status=JobStatus.PROCESSING)

            try:
                from transcribe import transcribe

                with self._lock:
                    job_ref = self._jobs.get(job_id)
                    input_path = job_ref.file_path if job_ref else None

                result = transcribe(
                    input_path=input_path,
                    url=url,
                    model=model,
                )

                with self._lock:
                    job = self._jobs.get(job_id)
                    key_id = job.key_id if job else ""

                if key_id:
                    increment_usage(key_id)

                self._update_job(
                    job_id,
                    status=JobStatus.COMPLETED,
                    completed_at=time.time(),
                    result=result,
                )

            except Exception as e:
                error_detail = {
                    "code": "PIPELINE_ERROR",
                    "message": str(e),
                }
                if "timeout" in str(e).lower():
                    error_detail["code"] = "UPSTREAM_TIMEOUT"
                    error_detail["action"] = "wait_and_retry"
                elif "429" in str(e) or "rate" in str(e).lower():
                    error_detail["code"] = "UPSTREAM_RATE_LIMITED"
                    error_detail["action"] = "wait_and_retry"

                self._update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    completed_at=time.time(),
                    error=error_detail,
                )

            finally:
                # Clean up temp file
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job and job.file_path:
                        try:
                            Path(job.file_path).unlink(missing_ok=True)
                        except OSError:
                            pass


class QuotaExceededError(Exception):
    def __init__(self, remaining: int = 0):
        self.remaining = remaining
        super().__init__(f"Monthly quota exceeded ({remaining} remaining)")


# Singleton
job_manager = JobManager()
