param(
  [string]$Owner = "crux2006",
  [string]$Repo = "tefas-fon-uyari"
)

$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot "scripts\run_workflow_with_prompt.ps1"
if (-not (Test-Path $runner)) {
  throw "run_workflow_with_prompt.ps1 bulunamadi: $runner"
}

$cmdPath = Join-Path $desktop "Fon Workflow Tetikle.cmd"
$cmdBody = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$runner" -Owner "$Owner" -Repo "$Repo"
"@
$cmdBody | Out-File -FilePath $cmdPath -Encoding ASCII -Force

$pagesUrl = "https://$Owner.github.io/$Repo/"
$actionsUrl = "https://github.com/$Owner/$Repo/actions/workflows/fund-alert-daily.yml"

$pagesShortcut = Join-Path $desktop "Fon Rapor Sayfasi.url"
$actionsShortcut = Join-Path $desktop "Fon Actions.url"
@"
[InternetShortcut]
URL=$pagesUrl
"@ | Out-File -FilePath $pagesShortcut -Encoding ASCII -Force

@"
[InternetShortcut]
URL=$actionsUrl
"@ | Out-File -FilePath $actionsShortcut -Encoding ASCII -Force

Write-Output "Masaustu kisayollari olusturuldu."
Write-Output "1) $cmdPath"
Write-Output "2) $pagesShortcut"
Write-Output "3) $actionsShortcut"
