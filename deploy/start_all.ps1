# 方案 A：启动两套 NapCat + 陪伴 + 摩卡 bot
$ErrorActionPreference = "Stop"

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port })
}

$mochaNapCat = "D:\NapCat.Shell.Windows.OneKey\NapCat.52230.Shell"
$companionNapCat = "D:\NapCatCompanion\NapCat.52230.Shell"

if (-not (Test-Port 6099)) {
    Start-Process -FilePath (Join-Path $mochaNapCat "NapCatWinBootMain.exe") `
        -ArgumentList "3826300285" -WorkingDirectory $mochaNapCat
    Write-Host "启动摩卡 NapCat（6099 / 3000，QQ 3826300285）"
}
if (-not (Test-Port 6100)) {
    Start-Process -FilePath (Join-Path $companionNapCat "NapCatWinBootMain.exe") `
        -ArgumentList "3848406242" -WorkingDirectory $companionNapCat
    Write-Host "启动陪伴 NapCat（6100 / 3001，QQ 3848406242）"
}
Start-Sleep -Seconds 8

if (-not (Test-Port 8765)) {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start_companion.ps1") `
        -WindowStyle Hidden
    Write-Host "启动陪伴工作台（8765）"
}
if (-not (Test-Port 8080)) {
    Start-ScheduledTask -TaskName "QQSettingBot" -ErrorAction SilentlyContinue
    Write-Host "启动摩卡 bot（8080）"
}
Write-Host "启动检查完成。" -ForegroundColor Green
