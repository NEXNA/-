# 打包陪伴工作台，用于上传云端
param(
    [switch]$IncludeData
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $Root "companion"
$stage = Join-Path $Root "dist\companion-package"
$zip = Join-Path $Root ("dist\companion-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".zip")
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null

robocopy $src $stage /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS `
    /XD "__pycache__" ".tmp-tests" "tmp-tests" "backups" "research" "archive" "data" ".acl-recovery" `
    /XF "*.pyc" ".env*" "server.out.log" "server.err.log" "app.out.log" "app.err.log"

if ($IncludeData) {
    $data = Join-Path $src "data"
    New-Item -ItemType Directory -Force (Join-Path $stage "data") | Out-Null
    Copy-Item (Join-Path $data "companion.db") (Join-Path $stage "data\companion.db") -Force
}
New-Item -ItemType Directory -Force (Split-Path $zip) | Out-Null
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
Write-Host "已打包：$zip" -ForegroundColor Green
Write-Host "未包含 .env；上传后在云端创建 .env。" -ForegroundColor Yellow
if (-not $IncludeData) { Write-Host "未包含数据库；需要迁移时加 -IncludeData。" }
