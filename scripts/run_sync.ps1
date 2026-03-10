param(
  [string]$BaseUrl = "https://crux2006.github.io/tefas-fon-uyari/",
  [string]$OutputDir = "$env:USERPROFILE\Desktop\FonRaporlari",
  [int]$StartHour = 11,
  [int]$StartMinute = 0,
  [int]$PollMinutes = 2,
  [int]$MaxPollAttempts = 120
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$syncScript = Join-Path $projectRoot "scripts\sync_latest_report.py"
$logDir = Join-Path $env:LOCALAPPDATA "FonRaporSync"
$logFile = Join-Path $logDir "sync.log"
$latestFile = Join-Path $OutputDir "latest_report.txt"

$mutexName = "FonRaporSyncSingleInstance"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasLock = $false

if (-not (Test-Path $syncScript)) {
  throw "sync_latest_report.py bulunamadi: $syncScript"
}

if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
if (-not (Test-Path $OutputDir)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$pythonCmd = Get-Command python -ErrorAction Stop
$pythonExe = $pythonCmd.Source

$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
"[$timestamp] Basladi" | Out-File -FilePath $logFile -Append -Encoding UTF8

try {
  $hasLock = $mutex.WaitOne(0)
  if (-not $hasLock) {
    $tsSkip = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$tsSkip] Baska bir FonRaporSync ornegi zaten calisiyor. Cikis." | Out-File -FilePath $logFile -Append -Encoding UTF8
    return
  }

  $now = Get-Date
  $target = Get-Date -Hour $StartHour -Minute $StartMinute -Second 0
  if ($now -lt $target) {
    $waitSec = [int]([Math]::Ceiling(($target - $now).TotalSeconds))
    $tsWait = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$tsWait] 11:00 oncesi, $waitSec saniye beklenecek." | Out-File -FilePath $logFile -Append -Encoding UTF8
    Start-Sleep -Seconds $waitSec
  }

  $todayKey = (Get-Date).ToString("yyyyMMdd")
  $done = $false

  for ($i = 1; $i -le $MaxPollAttempts; $i++) {
    & $pythonExe $syncScript --base-url $BaseUrl --output-dir $OutputDir 2>&1 | Out-File -FilePath $logFile -Append -Encoding UTF8

    $latest = ""
    if (Test-Path $latestFile) {
      $latest = (Get-Content $latestFile -Raw).Trim()
    }
    if ($latest -match "^\d{8}_\d{6}$" -and $latest.Substring(0,8) -eq $todayKey) {
      $tsOk = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
      "[$tsOk] Bugunun raporu alindi: $latest" | Out-File -FilePath $logFile -Append -Encoding UTF8
      $done = $true
      break
    }

    if ($i -lt $MaxPollAttempts) {
      $tsPoll = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
      "[$tsPoll] Bugunun raporu henuz yok (latest=$latest). $PollMinutes dk sonra tekrar denenecek. Deneme $i/$MaxPollAttempts" | Out-File -FilePath $logFile -Append -Encoding UTF8
      Start-Sleep -Seconds ([Math]::Max(1, $PollMinutes) * 60)
    }
  }

  if (-not $done) {
    $tsEnd = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$tsEnd] Maks deneme asildi; bugunun raporu bulunamadi." | Out-File -FilePath $logFile -Append -Encoding UTF8
  }

  $tsFinish = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[$tsFinish] Tamamlandi" | Out-File -FilePath $logFile -Append -Encoding UTF8
} catch {
  $tsErr = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[$tsErr] HATA: $($_.Exception.Message)" | Out-File -FilePath $logFile -Append -Encoding UTF8
} finally {
  if ($hasLock) {
    $mutex.ReleaseMutex() | Out-Null
  }
  $mutex.Dispose()
}
