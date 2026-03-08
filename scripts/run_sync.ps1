param(
  [string]$BaseUrl = "https://crux2006.github.io/tefas-fon-uyari/",
  [string]$OutputDir = "$env:USERPROFILE\Desktop\FonRaporlari"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$syncScript = Join-Path $projectRoot "scripts\sync_latest_report.py"
$logDir = Join-Path $env:LOCALAPPDATA "FonRaporSync"
$logFile = Join-Path $logDir "sync.log"

if (-not (Test-Path $syncScript)) {
  throw "sync_latest_report.py bulunamadi: $syncScript"
}

if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$pythonCmd = Get-Command python -ErrorAction Stop
$pythonExe = $pythonCmd.Source

$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
"[$timestamp] Basladi" | Out-File -FilePath $logFile -Append -Encoding UTF8

try {
  & $pythonExe $syncScript --base-url $BaseUrl --output-dir $OutputDir 2>&1 | Out-File -FilePath $logFile -Append -Encoding UTF8
  $tsOk = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[$tsOk] Tamamlandi" | Out-File -FilePath $logFile -Append -Encoding UTF8
} catch {
  $tsErr = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[$tsErr] HATA: $($_.Exception.Message)" | Out-File -FilePath $logFile -Append -Encoding UTF8
}
