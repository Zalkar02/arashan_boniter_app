$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "Arashan Boniter"
$RunScript = Join-Path $ProjectDir "run.ps1"
$IconPath = Join-Path $ProjectDir "assets\app_icon.ico"

if (-not (Test-Path $RunScript)) {
  Write-Host "run.ps1 not found: $RunScript"
  exit 1
}

$wsh = New-Object -ComObject WScript.Shell
$desktopDirs = @()
$desktopDirs += [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
if ($env:USERPROFILE) { $desktopDirs += (Join-Path $env:USERPROFILE "Desktop") }
if ($env:OneDrive) { $desktopDirs += (Join-Path $env:OneDrive "Desktop") }
$desktopDirs = $desktopDirs | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

if (-not $desktopDirs -or $desktopDirs.Count -eq 0) {
  throw "Desktop directory not found."
}

$created = @()
foreach ($desktopDir in $desktopDirs) {
  try {
    $shortcutPath = Join-Path $desktopDir "$AppName.lnk"
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""
    $shortcut.WorkingDirectory = $ProjectDir
    $shortcut.Description = "Система бонитировки"
    if (Test-Path $IconPath) {
      $shortcut.IconLocation = $IconPath
    }
    $shortcut.Save()
    if (Test-Path $shortcutPath) {
      $created += $shortcutPath
    }
  } catch {
    Write-Host "Failed to create shortcut in $desktopDir : $($_.Exception.Message)"
  }
}

if ($created.Count -eq 0) {
  throw "Shortcut was not created in any desktop directory."
}

Write-Host "Desktop shortcut created:"
foreach ($path in $created) {
  Write-Host "  $path"
}
