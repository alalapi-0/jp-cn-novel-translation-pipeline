#!/usr/bin/env python3
"""Serve the real Workbench UI/API with disposable synthetic state only."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()
    # This test server never reads .env or uses inherited provider credentials.
    for key in tuple(os.environ):
        if key.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_WEBHOOK_URL")):
            os.environ.pop(key, None)
    os.environ["REAL_API_TESTS_ENABLED"] = "false"
    os.environ.pop("ALLOW_LEGACY_REFINEMENT", None)
    from workbench.server import serve
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-fixture-", dir=cache) as directory:
        fixture = Path(directory)
        examples = fixture / "data/examples"
        examples.mkdir(parents=True)
        for source in (ROOT / "data/examples").glob("workbench_project.*.example.json"):
            shutil.copyfile(source, examples / source.name)
        print("Workbench synthetic fixture server; no production state or credentials", flush=True)
        serve(fixture, ROOT / "frontend", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
