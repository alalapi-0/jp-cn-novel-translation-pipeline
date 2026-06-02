"""Controlled run mode: explicit switch + checkpoint for resumable batches."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        if segment_id not in self.checkpoint.completed_segments:
            self.checkpoint.completed_segments.append(segment_id)
        self.checkpoint.spent_tokens += tokens
        self.checkpoint.spent_usd = round(self.checkpoint.spent_usd + cost_usd, 8)
        self.checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()

    def abort(self, reason: str) -> None:
        self.checkpoint.status = f"aborted:{reason}"
        self.checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()

    def complete(self) -> None:
        self.checkpoint.status = "completed"
        self.checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()

    def save(self) -> Path:
        self.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(
            json.dumps(asdict(self.checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.checkpoint_path

    def _load_or_create(self) -> ControlledRunCheckpoint:
        path = self.checkpoint_path
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return ControlledRunCheckpoint(**data)
        return ControlledRunCheckpoint(run_id=self.config.run_id)
