param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed. Check the Python interpreter." }
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed. Check network access and retry setup." }
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Resolve the error above before launching the bots." }

if (-not (Test-Path -LiteralPath "config\settings.json")) {
    Copy-Item -LiteralPath "config\settings.example.json" -Destination "config\settings.json"
}
if (-not (Test-Path -LiteralPath "config\outreach_settings.json")) {
    Copy-Item -LiteralPath "config\outreach_settings.example.json" -Destination "config\outreach_settings.json"
}
if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
}

Write-Host "Setup complete. Edit .env and config JSON files, then run scripts\test.ps1."
