param(
  [string]$BaseUrl = "https://crux2006.github.io/tefas-fon-uyari/",
  [string]$OutputDir = "$env:USERPROFILE\Desktop\FonRaporlari"
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
$ps = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$runner"" -BaseUrl ""$BaseUrl"" -OutputDir ""$OutputDir"""
$vbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "$ps", 0, False
"@
$vbs | Out-File -FilePath $vbsPath -Encoding ASCII -Force

Write-Output "Acilista otomatik indirme aktif edildi."
Write-Output "Startup dosyasi: $vbsPath"
Write-Output "Rapor klasoru: $OutputDir"
