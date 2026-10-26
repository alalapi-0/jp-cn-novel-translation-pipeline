"""Controlled run mode: explicit switch + checkpoint for resumable batches."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Replace one owned checkpoint atomically; retain the prior file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextmanager
def checkpoint_lock(path: Path):
    """Kernel-owned, nonblocking local checkpoint exclusion, not a global scheduler."""
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("checkpoint is already in use") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ControlledRunConfig:
    enabled: bool = False
    checkpoint_dir: Path = field(default_factory=lambda: Path("workspace/checkpoints"))
    run_id: str = "default"

    @classmethod
    def from_env(cls, checkpoint_dir: Path | None = None) -> ControlledRunConfig:
        return cls(
            enabled=_env_bool("CONTROLLED_RUN_ENABLED", False),
            checkpoint_dir=checkpoint_dir or Path("workspace/checkpoints"),
            run_id=os.environ.get("CONTROLLED_RUN_ID", "default"),
        )


@dataclass
class ControlledRunCheckpoint:
    run_id: str
    completed_segments: list[str] = field(default_factory=list)
    spent_usd: float = 0.0
    spent_tokens: int = 0
    status: str = "in_progress"
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class ControlledRunManager:
    def __init__(self, config: ControlledRunConfig) -> None:
        self.config = config
        self.checkpoint = self._load_or_create()

    @property
    def checkpoint_path(self) -> Path:
        return self.config.checkpoint_dir / f"{self.config.run_id}.json"

    def require_enabled(self) -> None:
        if not self.config.enabled:
            raise RuntimeError(
                "controlled run is disabled; set CONTROLLED_RUN_ENABLED=true with user authorization"
            )

    def is_segment_done(self, segment_id: str) -> bool:
        return segment_id in self.checkpoint.completed_segments

    def mark_segment_done(self, segment_id: str, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        candidate = deepcopy(self.checkpoint)
        if segment_id not in candidate.completed_segments:
            candidate.completed_segments.append(segment_id)
        candidate.spent_tokens += tokens
        candidate.spent_usd = round(candidate.spent_usd + cost_usd, 8)
        candidate.updated_at = datetime.now(timezone.utc).isoformat()
        self._commit(candidate)

    def abort(self, reason: str) -> None:
        candidate = deepcopy(self.checkpoint)
        candidate.status = f"aborted:{reason}"
        candidate.updated_at = datetime.now(timezone.utc).isoformat()
        self._commit(candidate)

    def complete(self) -> None:
        candidate = deepcopy(self.checkpoint)
        candidate.status = "completed"
        candidate.updated_at = datetime.now(timezone.utc).isoformat()
        self._commit(candidate)

    def _commit(self, candidate: ControlledRunCheckpoint) -> None:
        previous = self.checkpoint
        self.checkpoint = candidate
        try:
            self.save()
        except BaseException:
            self.checkpoint = previous
            raise

    def save(self) -> Path:
        atomic_write_json(self.checkpoint_path, asdict(self.checkpoint))
        return self.checkpoint_path

    def _load_or_create(self) -> ControlledRunCheckpoint:
        path = self.checkpoint_path
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(ControlledRunCheckpoint)}
            filtered = {k: v for k, v in data.items() if k in known}
            extra = {k: v for k, v in data.items() if k not in known}
            cp = ControlledRunCheckpoint(**filtered)
            if extra:
                cp.metadata.update(extra)
            return cp
        return ControlledRunCheckpoint(run_id=self.config.run_id)
