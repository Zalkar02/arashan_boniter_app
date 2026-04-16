param(
  [string]$PythonBin = "python"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"
$ReqFile = Join-Path $ProjectDir "requirements-windows.txt"

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Command
  )
  & $Command[0] $Command[1..($Command.Length - 1)]
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
  }
}

Set-Location $ProjectDir

if (-not (Get-Command $PythonBin -ErrorAction SilentlyContinue)) {
  Write-Host "Python not found: $PythonBin"
  exit 1
}

if (-not (Test-Path $VenvDir)) {
  Invoke-Checked @($PythonBin, "-m", "venv", $VenvDir)
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
if (-not (Test-Path $ReqFile)) {
  $ReqFile = Join-Path $ProjectDir "requirements.txt"
}

Invoke-Checked @($VenvPython, "-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked @($VenvPip, "install", "-r", $ReqFile)
Invoke-Checked @($VenvPython, "migrate_local_db.py")

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
