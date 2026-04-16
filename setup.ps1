param(
  [string]$PythonBin = "python"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"

Set-Location $ProjectDir

if (-not (Get-Command $PythonBin -ErrorAction SilentlyContinue)) {
  Write-Host "Python not found: $PythonBin"
  exit 1
}

if (-not (Test-Path $VenvDir)) {
  & $PythonBin -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPip install -r requirements.txt
& $VenvPython migrate_local_db.py

if ((Test-Path "$ProjectDir\.app_state\print_settings.example.json") -and -not (Test-Path "$ProjectDir\.app_state\print_settings.json")) {
  Copy-Item "$ProjectDir\.app_state\print_settings.example.json" "$ProjectDir\.app_state\print_settings.json"
}
if ((Test-Path "$ProjectDir\sheep_local.example.db") -and -not (Test-Path "$ProjectDir\sheep_local.db")) {
  Copy-Item "$ProjectDir\sheep_local.example.db" "$ProjectDir\sheep_local.db"
}
if ((Test-Path "$ProjectDir\last_sync.example.txt") -and -not (Test-Path "$ProjectDir\last_sync.txt")) {
  Copy-Item "$ProjectDir\last_sync.example.txt" "$ProjectDir\last_sync.txt"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run the app with: .\run.ps1"
