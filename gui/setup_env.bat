@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem 桌面版依赖安装: 在项目里建 .venv，避免装到 PATH 里随便哪个 python
set "MIRROR=https://mirrors.aliyun.com/pypi/simple/"

if exist ".venv\Scripts\python.exe" goto ready
echo [1/2] 创建 .venv ...
py -3 -m venv .venv 2>nul
if exist ".venv\Scripts\python.exe" goto ready
python -m venv .venv
if exist ".venv\Scripts\python.exe" goto ready
echo.
echo [失败] 没能创建 .venv，请确认本机有 Python 3.9+。
echo        也可以手动执行: python -m venv .venv
pause
exit /b 1

:ready
set "PY=.venv\Scripts\python.exe"
if exist "%PY%" goto install
set "PY=.venv\Scripts\python.exe"

:install
echo [2/2] 安装 pyside6-essentials + pillow ...
"%PY%" -m pip install --no-cache-dir -i %MIRROR% pyside6-essentials pillow
if not errorlevel 1 goto done
echo.
echo [失败] 安装没成功。官方源在国内常卡在几十 MB 不动，镜像一般几秒完成。
echo        镜像也失败的话换这个再试:
echo        "%PY%" -m pip install -i https://mirrors.cloud.tencent.com/pypi/simple/ pyside6-essentials pillow
pause
exit /b 1

:done
echo.
echo 完成。启动桌面版: gui\run_gui.bat
pause
exit /b 0
