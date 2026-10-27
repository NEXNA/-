@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if exist "%PY%" goto run

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
    goto run
)

set "PY=python"

:run
%PY% tools\setup.py
pause
