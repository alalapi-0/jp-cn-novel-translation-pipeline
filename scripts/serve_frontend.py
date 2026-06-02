#!/usr/bin/env python3
"""Serve frontend/ for local workbench smoke checks."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent / "frontend"
    if not root.is_dir():
        raise SystemExit(f"frontend directory not found: {root}")
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving {root} at http://127.0.0.1:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
