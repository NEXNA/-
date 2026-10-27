param([string]$ExtraArgs = "")

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "setup-24x7.ps1"
if (-not (Test-Path $script)) {
    throw "找不到 setup-24x7.ps1"
}
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" $ExtraArgs"
Write-Host "正在请求管理员权限..."
Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments
