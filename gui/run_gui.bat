@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem 优先用项目本地虚拟环境，免得 PATH 里哪个 python 先命中就装进了别的解释器
set "PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%PY%" goto check
set "PY=python"

:check
"%PY%" -c "import PySide6" >nul 2>&1
if not errorlevel 1 goto run
goto nodep

:run
"%PY%" gui\app.py %*
if errorlevel 1 pause
exit /b 0

:nodep
echo.
echo [缺少依赖] 当前解释器里没有 PySide6:
echo     %PY%
echo.
echo 两种修法，任选一种:
echo   1) 双击 gui\setup_env.bat   在项目里建 .venv 并装好（推荐，不污染全局）
echo   2) 手动装到上面那个解释器:
echo      "%PY%" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ pyside6-essentials pillow
echo.
echo 只想先用网页版: 双击 gui\run_web.bat （零依赖，不需要 PySide6）
echo.
pause
exit /b 1
