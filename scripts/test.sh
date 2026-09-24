#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment not found. Run scripts/setup.sh first." >&2
  exit 1
fi

.venv/bin/python -m compileall -q core utils tests app_tkinter.py outreach_ui.py run.py
.venv/bin/python -m pytest -q
.venv/bin/python -c "import app_tkinter, outreach_ui, core.main_script, core.outreach.outreach_pipeline; print('Import smoke test passed.')"
.venv/bin/python -m pip check
