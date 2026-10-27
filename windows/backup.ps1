$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $Root "data"

if (-not (Test-Path $data)) {
    Write-Host "没有 data 目录，先让机器人记录并整理一些内容。" -ForegroundColor Yellow
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dst = Join-Path $Root "backups\$stamp"
New-Item -ItemType Directory -Force $dst | Out-Null

Copy-Item $data (Join-Path $dst "data") -Recurse -Force
Copy-Item (Join-Path $Root "config.toml") $dst -Force
Copy-Item (Join-Path $Root "prompts") $dst -Recurse -Force
$stickers = Join-Path $Root "stickers"
if (Test-Path $stickers) {
    Copy-Item $stickers (Join-Path $dst "stickers") -Recurse -Force
}

$companionData = Join-Path $Root "companion\data"
if (Test-Path $companionData) {
    Copy-Item $companionData (Join-Path $dst "companion-data") -Recurse -Force
}

Write-Host "已备份到：$dst" -ForegroundColor Green
Write-Host "包含：data/、config.toml、prompts/、stickers/、companion-data/"
Write-Host "注意：没有复制 .env（密钥），恢复时请继续用你原来的 .env。" -ForegroundColor Yellow
