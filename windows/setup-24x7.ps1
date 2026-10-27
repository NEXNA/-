param(
    [string]$NapCatDir = "",
    [switch]$Undo,
    [switch]$DryRun,
    [switch]$QuickLogin
)

# 关闭 Windows 的「保存记忆/恢复上次应用」，并让 bot + NapCat 登录自启。
# 需要管理员权限；setup-windows.bat 会自动提权。

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BotTask = "QQSettingBot"
$NapCatTask = "NapCatAutoStart"

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Step {
    param([string]$Description, [scriptblock]$Action)
    if ($DryRun) {
        Write-Host "[dry-run] $Description"
        return
    }
    Write-Host "  - $Description"
    & $Action
}

function Find-NapCatDir {
    param([string]$Explicit)
    if ($Explicit) {
        if (Test-Path (Join-Path $Explicit "napcat.bat")) {
            return (Resolve-Path $Explicit).Path
        }
        throw "指定的目录里没有 napcat.bat：$Explicit"
    }
    $bases = @(
        "D:\NapCat.Shell.Windows.OneKey",
        "C:\NapCat.Shell.Windows.OneKey",
        (Join-Path $env:USERPROFILE "NapCat.Shell.Windows.OneKey")
    )
    foreach ($base in $bases) {
        if (-not (Test-Path $base)) { continue }
        $shells = Get-ChildItem -Path $base -Directory -Filter "NapCat.*.Shell" -ErrorAction SilentlyContinue
        foreach ($shell in $shells) {
            if (Test-Path (Join-Path $shell.FullName "napcat.bat")) {
                return $shell.FullName
            }
        }
        $hit = Get-ChildItem -Path $base -Recurse -Filter "napcat.bat" -ErrorAction SilentlyContinue |
            Where-Object { $_.DirectoryName -notlike "*\bootmain*" } |
            Select-Object -First 1
        if ($hit) { return $hit.DirectoryName }
    }
    return $null
}

function Get-NapCatQQ {
    param([string]$Dir)
    $files = Get-ChildItem -Path $Dir -Recurse -Filter "napcat_*.json" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "*protocol*" }
    foreach ($file in $files) {
        if ($file.BaseName -match '(\d{5,12})') {
            return $Matches[1]
        }
    }
    return $null
}

function Register-LogonTask {
    param(
        [string]$Name,
        [string]$Exe,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$Description
    )
    $action = New-ScheduledTaskAction -Execute $Exe -Argument $Arguments -WorkingDirectory $WorkingDirectory
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Settings $settings -Description $Description -Force | Out-Null
}

function Remove-TaskIfExists {
    param([string]$Name)
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
}

if (-not $DryRun -and -not (Test-Admin)) {
    throw "请以管理员身份运行：右键 setup-windows.bat → 以管理员身份运行"
}

Write-Host ""
Write-Host "QQ 设定整理机器人 · Windows 24h 在线设置"
Write-Host "项目目录：$Root"
if ($DryRun) { Write-Host "模式：DryRun（只显示，不修改系统）" }
Write-Host ""

if ($Undo) {
    Write-Host "撤销设置..."
    Invoke-Step "删除计划任务 $BotTask" { Remove-TaskIfExists $BotTask }
    Invoke-Step "删除计划任务 $NapCatTask" { Remove-TaskIfExists $NapCatTask }
    Invoke-Step "恢复休眠" { powercfg /hibernate on }
    Invoke-Step "恢复快速启动" {
        Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" `
            -Name HiberbootEnabled -Value 1 -Type DWord
    }
    Invoke-Step "恢复「重启后自动恢复应用」" {
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" `
            -Name RestartApps -Value 1 -Type DWord
    }
    Invoke-Step "恢复睡眠超时（30 分钟）" { powercfg /change standby-timeout-ac 30 }
    Invoke-Step "恢复休眠超时（180 分钟）" { powercfg /change hibernate-timeout-ac 180 }
    Invoke-Step "恢复合盖睡眠（交流电）" {
        powercfg /setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 1
        powercfg /setactive SCHEME_CURRENT
    }
    Write-Host ""
    Write-Host "已撤销。重启 Windows 后生效。"
    if (-not $DryRun) {
        Read-Host "按回车关闭" | Out-Null
    }
    return
}

$napcat = Find-NapCatDir -Explicit $NapCatDir
if ($napcat) {
    Write-Host "NapCat 目录：$napcat"
} else {
    Write-Host "NapCat 目录：未找到（只注册 bot 自启；可用 -NapCatDir 指定）" -ForegroundColor Yellow
}
Write-Host ""

# 1. 电源：主机不睡、不休眠、合盖不动
Invoke-Step "交流电下永不睡眠" { powercfg /change standby-timeout-ac 0 }
Invoke-Step "电池下永不睡眠" { powercfg /change standby-timeout-dc 0 }
Invoke-Step "关闭休眠（同时关闭快速启动）" { powercfg /hibernate off }
Invoke-Step "关闭硬盘超时" { powercfg /change disk-timeout-ac 0 }
Invoke-Step "关闭显示器超时（10 分钟，仅关屏幕）" { powercfg /change monitor-timeout-ac 10 }
Invoke-Step "合盖不睡眠（交流电）" {
    powercfg /setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 0
    powercfg /setactive SCHEME_CURRENT
}

# 2. 关闭 Windows 的「保存记忆」
Invoke-Step "关闭快速启动（HiberbootEnabled=0）" {
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" `
        -Name HiberbootEnabled -Value 0 -Type DWord
}
$winlogon = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
if (-not (Test-Path $winlogon)) {
    New-Item -Path $winlogon -Force | Out-Null
}
Invoke-Step "关闭「重启后自动恢复上次应用」（RestartApps=0）" {
    Set-ItemProperty -Path $winlogon -Name RestartApps -Value 0 -Type DWord
}

# 3. 登录自启
Invoke-Step "注册 bot 登录自启（$BotTask）" {
    $args = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Root\run.ps1`""
    Register-LogonTask -Name $BotTask -Exe "powershell.exe" -Arguments $args `
        -WorkingDirectory $Root -Description "QQ 设定整理机器人"
}
if ($napcat) {
    $napcatBat = Join-Path $napcat "napcat.bat"
    if ($QuickLogin) {
        $qq = Get-NapCatQQ -Dir $napcat
        if (-not $qq) {
            throw "找不到机器人 QQ 号，无法生成快速登录脚本；请用 -NapCatDir 指定目录"
        }
        $autoBat = Join-Path $Root "windows\napcat-autostart.bat"
        Invoke-Step "生成快速登录脚本（QQ $qq）" {
            $lines = @(
                '@echo off',
                'chcp 65001 >nul',
                "cd /d `"$napcat`"",
                ".\NapCatWinBootMain.exe $qq"
            )
            Set-Content -Path $autoBat -Value $lines -Encoding ASCII
        }
        $napcatBat = $autoBat
        Write-Host "NapCat 快速登录：已启用（QQ $qq）" -ForegroundColor Green
    } else {
        $quickBat = Join-Path $napcat "napcat.quick.bat"
        if (Test-Path $quickBat) {
            $quickText = Get-Content $quickBat -Raw -ErrorAction SilentlyContinue
            if ($quickText -match 'NapCatWinBootMain\.exe\s+(\d{5,12})' -and $Matches[1] -ne '10086') {
                $napcatBat = $quickBat
                Write-Host "NapCat 快速登录：QQ $($Matches[1])" -ForegroundColor Green
            } else {
                Write-Host "NapCat 快速登录未配置（quick.bat 里还是 10086），将用普通登录，可能需要扫码。" -ForegroundColor Yellow
            }
        }
    }
    Invoke-Step "注册 NapCat 登录自启（$NapCatTask）" {
        Register-LogonTask -Name $NapCatTask -Exe "cmd.exe" -Arguments "/c `"$napcatBat`"" `
            -WorkingDirectory $napcat -Description "NapCat QQ 协议端"
    }
}

Write-Host ""
Write-Host "完成。重启 Windows 后：" -ForegroundColor Green
Write-Host "  1. 登录 Windows 桌面（计划任务只在登录后运行）"
Write-Host "  2. 等 30-60 秒，双击 status.bat 检查"
Write-Host "  3. 群里发 @机器人 帮助"
Write-Host ""
Write-Host "撤销：以管理员运行 powershell -ExecutionPolicy Bypass -File .\windows\setup-24x7.ps1 -Undo"
if (-not $DryRun) {
    Read-Host "按回车关闭" | Out-Null
}
