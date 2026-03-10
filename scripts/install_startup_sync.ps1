param(
  [string]$BaseUrl = "https://crux2006.github.io/tefas-fon-uyari/",
  [string]$OutputDir = "$env:USERPROFILE\Desktop\FonRaporlari",
  [int]$StartHour = 11,
  [int]$StartMinute = 0,
  [int]$PollMinutes = 2,
  [int]$MaxPollAttempts = 120
)

$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot "scripts\run_sync.ps1"

if (-not (Test-Path $runner)) {
  throw "run_sync.ps1 bulunamadi: $runner"
}

if (-not (Test-Path $OutputDir)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$vbsPath = Join-Path $startupDir "FonRaporSync.vbs"
$cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -BaseUrl "{1}" -OutputDir "{2}" -StartHour {3} -StartMinute {4} -PollMinutes {5} -MaxPollAttempts {6}' -f `
  $runner, $BaseUrl, $OutputDir, $StartHour, $StartMinute, $PollMinutes, $MaxPollAttempts
$cmdEscaped = $cmd.Replace('"', '""')
$vbs = "Set WshShell = CreateObject(""WScript.Shell"")`r`nWshShell.Run ""$cmdEscaped"", 0, False`r`n"
$vbs | Out-File -FilePath $vbsPath -Encoding ASCII -Force

Write-Output "Acilista otomatik indirme aktif edildi."
Write-Output "Startup dosyasi: $vbsPath"
Write-Output "Rapor klasoru: $OutputDir"
Write-Output "Calisma zamani: her acilista baslar, 11:00'dan once bekler, 11:00'dan sonra periyodik kontrol eder."
