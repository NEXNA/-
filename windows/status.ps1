param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Test-Port {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1200)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync($HostName, $Port)
        if ($task.Wait($TimeoutMs) -and $client.Connected) {
            $client.Close()
            return $true
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

function Read-EnvValue {
    param([string]$Key)
    $path = Join-Path $Root ".env"
    if (-not (Test-Path $path)) { return "" }
    $line = Get-Content $path -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } |
        Select-Object -First 1
    if (-not $line) { return "" }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

Write-Host ""
Write-Host "QQ 设定整理机器人 · 状态检查"
Write-Host "项目：$Root"
Write-Host ("-" * 50)

$botOk = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/healthz" -TimeoutSec 3
    Write-Host "[OK]   bot webhook  http://127.0.0.1:8080" -ForegroundColor Green
    $botOk = $true
} catch {
    Write-Host "[DOWN] bot webhook  http://127.0.0.1:8080" -ForegroundColor Red
}

$napcatPort = Test-Port -HostName "127.0.0.1" -Port 3000
if ($napcatPort) {
    Write-Host "[OK]   NapCat API   http://127.0.0.1:3000" -ForegroundColor Green
} else {
    Write-Host "[DOWN] NapCat API   http://127.0.0.1:3000" -ForegroundColor Red
}

$token = Read-EnvValue -Key "ONEBOT_ACCESS_TOKEN"
if ($napcatPort -and $token) {
    try {
        $status = Invoke-RestMethod `
            -Uri "http://127.0.0.1:3000/get_status" `
            -Method Post -Body "{}" -ContentType "application/json" `
            -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 3
        $online = $status.data.online
        if ($online) {
            Write-Host "[OK]   QQ 在线" -ForegroundColor Green
        } else {
            Write-Host "[WAIT] NapCat 已启动，但 QQ 还没登录" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] NapCat API Token 不对，或还没加载新配置" -ForegroundColor Yellow
    }
}

Write-Host ("-" * 50)
if (-not $botOk) {
    Write-Host "bot 没起来：双击 start.bat，或看 logs\bot.log" -ForegroundColor Yellow
}
if (-not $napcatPort) {
    Write-Host "NapCat 没起来：到 D:\NapCat...\NapCat.52230.Shell 运行 napcat.bat" -ForegroundColor Yellow
}
if ($botOk -and $napcatPort) {
    Write-Host "两个服务都在。去群里发：@青叶摩卡 帮助" -ForegroundColor Green
}

$log = Join-Path $Root "logs\bot.log"
if (Test-Path $log) {
    Write-Host ""
    Write-Host "最近 5 行 bot 日志："
    Get-Content $log -Tail 5 -Encoding UTF8
}
