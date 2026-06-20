# Final Consistency Report

Generated: 2026-06-18T06:13:17Z

Scope: chapters 1-612, 79632 segments.

## Result

- Final fixer dry-run changed segments: 0
- Final term variance: 0
- Final unrecognized variants: 0
- Target kana residuals: 0
- Target placeholder residuals: 0
- Target English residuals: 0
- Exported chapters: 612 / 612
- Singleton final translation check: passed

## Canonical Output

- Final translation: `output_cn/translated/full_volume_cn.md`
- Export manifest: `output_cn/final_export_manifest.json`
- JSON report: `workspace/review/final_consistency_report_20260618.json`
- Patch log: `workspace/review/final_consistency_patch_log_20260618.json`

Only the full Chinese volume is the final translation handoff. Per-chapter and bilingual files are regenerable working artifacts and are not retained as final copies.

## Cleanup

- Removed stale review files: 3
- Removed old round/log entries: {'workspace/logs': 148, 'workspace/round_reports': 28, 'artifacts': 6}
- Preserved source files, canonical run data, checkpoints, baseline, and API secrets.

## Reuse

Future works should follow `docs/translation_consistency_protocol.md`: source/current-text evidence first, glossary as locked hints only, source-conditioned rules, dry-run before apply, zero-change final dry-run, and singleton final export.
