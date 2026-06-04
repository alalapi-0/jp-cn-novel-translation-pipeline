#!/usr/bin/env python3
"""Serve frontend/ and Workbench /api endpoints for local smoke checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.server import serve  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5174)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    frontend_root = REPO_ROOT / "frontend"
    if not frontend_root.is_dir():
        raise SystemExit(f"frontend directory not found: {frontend_root}")
    serve(REPO_ROOT, frontend_root, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
