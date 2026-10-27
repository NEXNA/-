# 启动陪伴工作台专用 NapCat（3848406242）
$Root = "D:\NapCatCompanion\NapCat.52230.Shell"
$exe = Join-Path $Root "NapCatWinBootMain.exe"
if (-not (Test-Path $exe)) {
    Write-Host "找不到 $exe" -ForegroundColor Red
    exit 1
}
Start-Process -FilePath $exe -ArgumentList "3848406242" -WorkingDirectory $Root
Write-Host "已启动陪伴 NapCat：6100 / 3001" -ForegroundColor Green
Start-Sleep -Seconds 10
$python = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (Test-Path $python) {
    & $python (Join-Path $PSScriptRoot "ensure_event_client.py") `
        --webui "http://127.0.0.1:6100" `
        --token "replace-with-napcat-webui-token" `
        --name "陪伴工作台" `
        --url "http://127.0.0.1:8765/napcat/event?token=replace-me"
}
