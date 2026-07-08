"""In-process download job registry.

One job per source (``"abn"`` / ``"paypal"``); worker threads run Playwright's
sync API off the asyncio event loop.  All mutations are protected by a single lock.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    PENDING = "pending"
    WAITING_FOR_AUTH = "waiting-for-auth"
    DOWNLOADING = "downloading"
    IMPORTING = "importing"
    DONE = "done"
    FAILED = "failed"


_TERMINAL = {JobState.DONE, JobState.FAILED}


@dataclass
class DownloadJob:
    source: str
    state: JobState = JobState.PENDING
    message: str = ""
    import_summary: dict[str, Any] | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None

    def is_terminal(self) -> bool:
        return self.state in _TERMINAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "state": self.state,
            "message": self.message,
            "import_summary": self.import_summary,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class JobRegistry:
    """Thread-safe registry; one active job per download source."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, DownloadJob] = {}

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get(self, source: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(source)

    def is_running(self, source: str) -> bool:
        """True when a job for *source* is in a non-terminal state."""
        job = self.get(source)
        return job is not None and not job.is_terminal()

    # ------------------------------------------------------------------
    # Write helpers (all protected by the lock)
    # ------------------------------------------------------------------

    def create(self, source: str) -> DownloadJob:
        """Create (or replace) a job for *source* in PENDING state."""
        with self._lock:
            job = DownloadJob(source=source)
            self._jobs[source] = job
            return job

    def update_state(
        self, source: str, state: JobState, message: str = ""
    ) -> DownloadJob | None:
        """Transition *source* job to *state*.  Returns the job, or None if not found."""
        with self._lock:
            job = self._jobs.get(source)
            if job is None:
                return None
            job.state = state
            job.message = message
            if state in _TERMINAL:
                job.finished_at = datetime.utcnow()
            return job

    def set_summary(self, source: str, summary: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(source)
            if job:
                job.import_summary = summary


# ---------------------------------------------------------------------------
# Module-level singleton — importable by routers and downloader threads alike.
# ---------------------------------------------------------------------------

_registry = JobRegistry()


def get_registry() -> JobRegistry:
    return _registry
