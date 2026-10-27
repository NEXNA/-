@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYW=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"
set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0control_panel.py"
    exit /b 0
)
if exist "%PY%" (
    start "" "%PY%" "%~dp0control_panel.py"
    exit /b 0
)
start "" pythonw "%~dp0control_panel.py"
if errorlevel 1 (
    echo 找不到 Python，请先运行 run.ps1 确认 Python 可用。
    pause
)
