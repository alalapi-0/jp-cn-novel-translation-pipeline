# Final Consistency Report

Generated: 2026-06-18T03:57:09Z

Scope: chapters 1-612, 79632 segments.

## Result

- Final fixer dry-run changed segments: 0
- Final term variance: 0
- Final unrecognized variants: 0
- Target kana residuals: 0
- Target placeholder residuals: 0
- Target English residuals: 0
- Exported chapters: 612 / 612

## What Changed

- Refreshed rules from actual full-book source/current-translation evidence, ignoring stale CA reports.
- Applied 332 high-confidence segment fixes across two passes.
- Corrected overbroad legacy behavior for 蕾雅/布兰/复活 by using segment-scoped fixes or contextual suppressions.
- Preserved スナイパーアント as 狙击蚁 while fixing 狙撃兵 as 狙击兵.
- Exported the final Chinese volume and bilingual volume from the same canonical files used by the fixer.

## Final Outputs

- Chinese volume: `output_cn/translated/full_volume_cn.md`
- Bilingual volume: `output_cn/bilingual/full_volume_bilingual.md`
- Export manifest: `output_cn/final_export_manifest.json`
- Patch log: `workspace/review/final_consistency_patch_log_20260618.json`
- JSON report: `workspace/review/final_consistency_report_20260618.json`

## Cleanup

Removed stale consistency logs/reports and 57 obsolete per-range supplement scripts so future review should use this report, the final JSON/patch log, and the fullbook regenerated rules as the audit source.
