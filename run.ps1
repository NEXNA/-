# 启动「青叶摩卡的面包坊」（崩溃后自动重启）
# 用法：右键「使用 PowerShell 运行」，或在终端执行 .\run.ps1

$ErrorActionPreference = "Stop"
$Root = "D:\青叶摩卡的面包坊"
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$candidates = @()
if ($env:QQBOT_PYTHON) { $candidates += $env:QQBOT_PYTHON }
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
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    } catch {
        continue
    }
}
if (-not $python) {
    Write-Host "找不到可用的 Python。请安装 Python 3.11+，或设置环境变量 QQBOT_PYTHON 指向 python.exe" -ForegroundColor Red
    exit 1
}

Write-Host "使用 Python：$python"
while ($true) {
    & $python -m bot
    $code = $LASTEXITCODE
    if ($code -eq 2 -or $code -eq 3) {
        Write-Host "启动失败（配置错误或端口被占用），已停止。看上面的报错。" -ForegroundColor Red
        exit $code
    }
    if ($code -eq 0) {
        Write-Host "已正常停止。"
        exit 0
    }
    Write-Host "机器人异常退出（代码 $code），5 秒后重启…" -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
