$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run scripts\setup.ps1 first."
}

Set-Location -LiteralPath $ProjectRoot
& $Python -m compileall -q core utils tests app_tkinter.py outreach_ui.py run.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -c "import app_tkinter, outreach_ui, core.main_script, core.outreach.outreach_pipeline; print('Import smoke test passed.')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pip check
exit $LASTEXITCODE
