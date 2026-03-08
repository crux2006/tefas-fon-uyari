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
$inputsFile = Join-Path $stateDir "workflow_inputs.json"

if (-not (Test-Path $tokenFile)) {
  $tok = Read-Host "GitHub PAT token gir (bir kere sorulur, yerelde saklanir)"
  if (-not $tok) {
    throw "Token bos olamaz."
  }
  $tok.Trim() | Out-File -FilePath $tokenFile -Encoding ASCII -Force
  Write-Host "Token kaydedildi: $tokenFile"
}

$last = @{
  sendTelegram = "E"
  totalTl = ""
  holdings = ""
}
if (Test-Path $inputsFile) {
  try {
    $obj = Get-Content $inputsFile -Raw | ConvertFrom-Json
    if ($obj.sendTelegram) { $last.sendTelegram = [string]$obj.sendTelegram }
    if ($obj.totalTl) { $last.totalTl = [string]$obj.totalTl }
    if ($obj.holdings) { $last.holdings = [string]$obj.holdings }
  } catch { }
}

$sendTg = Read-Host "Telegram gonderilsin mi? (E/H, varsayilan $($last.sendTelegram))"
if (-not $sendTg) { $sendTg = $last.sendTelegram }
$sendTelegram = "true"
if ($sendTg.Trim().ToLower().StartsWith("h")) { $sendTelegram = "false" }

$totalTl = Read-Host "Portfoy toplam TL (bos=son deger: $($last.totalTl))"
if (-not $totalTl) { $totalTl = $last.totalTl }
$holdings = Read-Host "Portfoy dagilimi (ornek TLY:40,PBR:35,TKZ:25) (bos=son deger: $($last.holdings))"
if (-not $holdings) { $holdings = $last.holdings }

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

$persist = @{
  sendTelegram = $(if ($sendTelegram -eq "true") { "E" } else { "H" })
  totalTl = [string]$totalTl
  holdings = [string]$holdings
} | ConvertTo-Json
$persist | Out-File -FilePath $inputsFile -Encoding UTF8 -Force

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
