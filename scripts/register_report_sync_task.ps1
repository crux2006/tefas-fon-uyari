param(
  [string]$TaskName = "FonRaporSync",
  [string]$BaseUrl = "https://crux2006.github.io/tefas-fon-uyari/",
  [string]$OutputDir = "$env:USERPROFILE\Desktop\FonRaporlari",
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$syncScript = Join-Path $projectRoot "scripts\sync_latest_report.py"

if (-not (Test-Path $syncScript)) {
  throw "sync_latest_report.py bulunamadi: $syncScript"
}

$actionArgs = "`"$syncScript`" --base-url `"$BaseUrl`" --output-dir `"$OutputDir`""
$taskCommand = "$PythonExe $actionArgs"

# schtasks kullanimi, kullanici yetkisiyle (admin gerektirmeden) ONLOGON task olusturur.
$escapedCommand = $taskCommand.Replace('"', '\"')
$createCmd = "schtasks /Create /F /SC ONLOGON /TN `"$TaskName`" /TR `"$escapedCommand`" /RL LIMITED"
$output = cmd /c $createCmd 2>&1
if ($LASTEXITCODE -ne 0) {
  throw "Task olusturma basarisiz. Cikti: $output"
}

Write-Output "Scheduled task olusturuldu: $TaskName"
Write-Output "Kaynak: $BaseUrl"
Write-Output "Hedef: $OutputDir"
