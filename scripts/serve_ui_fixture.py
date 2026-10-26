#!/usr/bin/env python3
"""Serve the real Workbench UI/API with disposable synthetic state only."""
from __future__ import annotations

import argparse
import json
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
    from isolated_checks import require_view
    require_view()
    from workbench.server import serve
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-fixture-", dir=cache) as directory:
        fixture = Path(directory)
        examples = fixture / "data/examples"
        examples.mkdir(parents=True)
        for source in (ROOT / "data/examples").glob("workbench_project.*.example.json"):
            shutil.copyfile(source, examples / source.name)
        # Explicit negative fixture: preserve an unavailable-native admission.
        # UI tests exercise the actual HTTP refusal path without ever trying
        # to start Codex, inspect a login or issue a model/approval decision.
        from workbench import native_agent
        manager, _ = native_agent._gate(fixture)
        native_agent._save_gate(manager, {'schema':1,'attempts':[{
            'input_fingerprint':native_agent._configuration_input(fixture),
            'status':'failed','error_class':'SyntheticNativeUnavailable',
            'synthetic_fixture':True,
        }]})
        (ROOT / ".ui-fixture-root.json").write_text(json.dumps({"root":str(fixture),"synthetic_only":True}))
        print("Workbench synthetic fixture server; no production state or credentials", flush=True)
        serve(fixture, ROOT / "frontend", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
