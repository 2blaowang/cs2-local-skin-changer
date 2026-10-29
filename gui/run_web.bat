@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem 网页版: 只用标准库，任何 python 3.9+ 都能跑，不需要 PySide6
set "PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%PY%" goto run
set "PY=python"

:run
"%PY%" gui\serve.py %*
if errorlevel 1 pause
exit /b 0
