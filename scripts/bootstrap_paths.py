"""Ensure model-router/src is importable from pipeline scripts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_ROUTER_SRC = REPO_ROOT / "model-router" / "src"
SRC_ROOT = REPO_ROOT / "src"


def bootstrap_paths(*, include_model_router: bool = True) -> None:
    for path in (SRC_ROOT, MODEL_ROUTER_SRC if include_model_router else None):
        if path is None:
            continue
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
