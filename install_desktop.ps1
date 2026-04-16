$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "Arashan Boniter"
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopDir "$AppName.lnk"
$RunScript = Join-Path $ProjectDir "run.ps1"
$IconPath = Join-Path $ProjectDir "assets\app_icon.ico"

if (-not (Test-Path $RunScript)) {
  Write-Host "run.ps1 not found: $RunScript"
  exit 1
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""
$shortcut.WorkingDirectory = $ProjectDir
$shortcut.Description = "Система бонитировки"
if (Test-Path $IconPath) {
  $shortcut.IconLocation = $IconPath
}
$shortcut.Save()

Write-Host "Desktop shortcut created:"
Write-Host "  $ShortcutPath"
