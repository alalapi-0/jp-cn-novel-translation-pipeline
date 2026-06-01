# Cursor Translation Pipeline Round Prompt

You are **Cursor**, a development assistant that works on the local repository.

## Your responsibilities for this round
- Implement the draft translation script (`scripts/translate_draft.py`).
- Ensure the script respects the `.env.example` placeholder and runs in **dry‑run** mode by default.
- Add command‑line arguments to specify a single chapter file and optional character range.
- Write generated drafts to `output_cn/experiments/` without touching the official `output_cn/translated/` directory.
- Update `config/openrouter.example.yaml` with the model mapping and runtime options (dry‑run, no overwrite).
- Create an empty placeholder file `output_cn/experiments/.gitkeep` so the experiments folder is tracked.
- Do **not** invoke any real OpenRouter API calls; just generate plan logs.

## Expected output
- `scripts/translate_draft.py` – a runnable Python script with placeholder implementation.
- `config/openrouter.example.yaml` – example configuration file (see the OpenRouter API test plan).
- `output_cn/experiments/.gitkeep` – an empty file.
- Updated `docs/reports/translation_project_scan_report.md` if needed (optional).

Once you finish, the repository should contain the new script, config, and keep‑alive file, ready for the next round.
