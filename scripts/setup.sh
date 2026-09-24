#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

[[ -f config/settings.json ]] || cp config/settings.example.json config/settings.json
[[ -f config/outreach_settings.json ]] || cp config/outreach_settings.example.json config/outreach_settings.json
[[ -f .env ]] || cp .env.example .env

echo "Setup complete. Edit .env and config JSON files, then run scripts/test.sh."
