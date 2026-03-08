param(
  [string]$Owner = "crux2006",
  [string]$Repo = "tefas-fon-uyari"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$dispatchPy = Join-Path $projectRoot "scripts\dispatch_workflow.py"
if (-not (Test-Path $dispatchPy)) {
  throw "dispatch_workflow.py bulunamadi: $dispatchPy"
}

$stateDir = Join-Path $env:LOCALAPPDATA "FonRaporSync"
if (-not (Test-Path $stateDir)) {
  New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
}
$tokenFile = Join-Path $stateDir "github_pat.txt"

if (-not (Test-Path $tokenFile)) {
  $tok = Read-Host "GitHub PAT token gir (bir kere sorulur, yerelde saklanir)"
  if (-not $tok) {
    throw "Token bos olamaz."
  }
  $tok.Trim() | Out-File -FilePath $tokenFile -Encoding ASCII -Force
  Write-Host "Token kaydedildi: $tokenFile"
}

$sendTg = Read-Host "Telegram gonderilsin mi? (E/H, varsayilan E)"
if (-not $sendTg) { $sendTg = "E" }
$sendTelegram = "true"
if ($sendTg.Trim().ToLower().StartsWith("h")) { $sendTelegram = "false" }

$totalTl = Read-Host "Portfoy toplam TL (bos birakirsan mevcut cloud portfoy korunur)"
$holdings = Read-Host "Portfoy dagilimi (ornek TLY:40,PBR:35,TKZ:25) - bos birakabilirsin"

$args = @(
  $dispatchPy,
  "--owner", $Owner,
  "--repo", $Repo,
  "--workflow", "fund-alert-daily.yml",
  "--token-file", $tokenFile,
  "--send-telegram", $sendTelegram
)

if ($totalTl) { $args += @("--portfolio-total-tl", $totalTl.Trim()) }
if ($holdings) { $args += @("--portfolio-holdings", $holdings.Trim()) }

$output = & python @args
$output | ForEach-Object { Write-Host $_ }

$runUrl = ($output | Where-Object { $_ -like "RUN_URL=*" } | Select-Object -First 1)
$pagesUrl = ($output | Where-Object { $_ -like "PAGES_URL=*" } | Select-Object -First 1)

if ($runUrl) {
  $u = $runUrl.Substring("RUN_URL=".Length)
  Start-Process $u | Out-Null
}
if ($pagesUrl) {
  $u2 = $pagesUrl.Substring("PAGES_URL=".Length)
  Start-Process $u2 | Out-Null
}

Write-Host "Workflow tetiklendi. Run ve rapor sayfasi acildi."
