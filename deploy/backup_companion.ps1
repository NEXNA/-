# 备份陪伴工作台数据库和角色配置
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dst = Join-Path $Root "backups\companion-$stamp"
New-Item -ItemType Directory -Force $dst | Out-Null

$db = Join-Path $Root "companion\data\companion.db"
if (Test-Path $db) {
    Copy-Item $db (Join-Path $dst "companion.db") -Force
}
$envFile = Join-Path $Root "companion\.env"
if (Test-Path $envFile) {
    Copy-Item $envFile (Join-Path $dst ".env.secret") -Force
}
Write-Host "已备份到 $dst" -ForegroundColor Green
Write-Host "注意：.env.secret 含密钥，不要外发。"
