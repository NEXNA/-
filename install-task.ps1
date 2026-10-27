# 把机器人注册成“登录 Windows 后自动启动”的计划任务。
# 需要以管理员身份运行 PowerShell。
#   .\install-task.ps1            安装/更新
#   .\install-task.ps1 -Remove    卸载
#   .\install-task.ps1 -Start     安装后立即启动

param(
    [switch]$Remove,
    [switch]$Start
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "QQSettingBot"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已卸载计划任务：$TaskName"
    exit 0
}

if (-not (Test-Path (Join-Path $Root "run.ps1"))) {
    throw "找不到 run.ps1，请在项目目录里运行这个脚本"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Root\run.ps1`"" `
    -WorkingDirectory $Root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "QQ 群设定整理机器人（NapCat + DeepSeek）" `
    -Force | Out-Null

Write-Host "已注册计划任务：$TaskName（登录后自动启动）"
if ($Start) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "已启动。查看日志：$Root\logs\bot.log"
}
