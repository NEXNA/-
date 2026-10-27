# 陪伴工作台 · 云端/第二台 Windows 启动器
# 用法：powershell -ExecutionPolicy Bypass -File .\start_companion.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$candidates = @()
if ($env:COMPANION_PYTHON) { $candidates += $env:COMPANION_PYTHON }
$candidates += (Join-Path $Root ".venv\Scripts\python.exe")
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd -and $pythonCmd.Source -and $pythonCmd.Source -notlike "*\WindowsApps\*") {
    $candidates += $pythonCmd.Source
}
$candidates += (Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe")

$python = $null
foreach ($candidate in $candidates) {
    if (-not $candidate -or -not (Test-Path $candidate)) { continue }
    try {
        & $candidate -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    } catch { continue }
}
if (-not $python) {
    Write-Host "找不到 Python。设置 COMPANION_PYTHON 指向 python.exe。" -ForegroundColor Red
    exit 1
}

Write-Host "陪伴工作台：$Root" -ForegroundColor Green
Write-Host "Python：$python"
while ($true) {
    & $python app.py --no-open
    $code = $LASTEXITCODE
    if ($code -eq 0) { exit 0 }
    Write-Host "异常退出（$code），5 秒后重启…" -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
