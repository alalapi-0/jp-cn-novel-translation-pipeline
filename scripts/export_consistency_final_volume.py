#!/usr/bin/env python3
"""Export one explicitly pinned accepted revision; never discover by mtime."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))
from translation.canonical_export import export_accepted_revision
from workbench.review_state import get_project_review_state, review_state_path


def export_final(output_root, include_chapters=False, include_bilingual=False, *, selection_manifest=None,
                 selection_sha256=None, repo_root=REPO_ROOT):
    if selection_manifest is None or not selection_sha256:
        raise ValueError('explicit pinned selection manifest and SHA256 required')
    if include_chapters or include_bilingual:
        raise ValueError('chapter/bilingual previews must use auxiliary export; canonical output is singleton')
    root = Path(repo_root); path = Path(selection_manifest)
    if not path.is_absolute(): path = root / path
    manifest_root = root / 'workspace/manifests'
    if (path.is_symlink() or any(p.is_symlink() for p in path.parents)
            or not path.resolve().is_relative_to(manifest_root.resolve()) or not path.is_file()):
        raise ValueError('ordinary project selection manifest required')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != selection_sha256: raise ValueError('selection manifest version changed')
    data = json.loads(raw)
    review_path = review_state_path(root)
    review_raw = review_path.read_bytes() if review_path.is_file() else None
    if review_path.is_symlink(): raise ValueError('unmanaged review state')
    review = get_project_review_state(root, data['project_id'])['segments']
    def check():
        if path.read_bytes() != raw: raise RuntimeError('selection manifest changed during export')
        now = review_path.read_bytes() if review_path.is_file() else None
        if now != review_raw: raise RuntimeError('review state changed during export')
    return export_accepted_revision(root, data, review, output_root=output_root, before_commit=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-manifest', type=Path, required=True)
    parser.add_argument('--selection-sha256', required=True)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    try:
        result = export_final(args.output_root, selection_manifest=args.selection_manifest, selection_sha256=args.selection_sha256)
    except (ValueError, RuntimeError, KeyError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps({key: result[key] for key in ('project_id', 'bundle_revision', 'chapters_exported', 'segments_exported')}, ensure_ascii=False))
    return 0

if __name__ == '__main__': raise SystemExit(main())
