@echo off
setlocal
set "APP_ROOT=%~dp0app"
set "APP_VENV=%LOCALAPPDATA%\bilibili-network\app-venv"
set "PYTHON=%APP_VENV%\Scripts\python.exe"
set "PYTHONW=%APP_VENV%\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
    py -3 -m venv "%APP_VENV%"
    if errorlevel 1 goto :failed
)
"%PYTHON%" -c "import imageio_ffmpeg, yt_dlp, PySide6.QtWebEngineWidgets, PySide6.QtWebView"
if errorlevel 1 (
    "%PYTHON%" -m pip install -r "%APP_ROOT%\requirements.txt"
    if errorlevel 1 goto :failed
    "%PYTHON%" -c "import imageio_ffmpeg, yt_dlp, PySide6.QtWebEngineWidgets, PySide6.QtWebView"
    if errorlevel 1 goto :failed
)
start "" "%PYTHONW%" "%APP_ROOT%\main.py"
if errorlevel 1 goto :failed
exit /b 0

:failed
echo Bilibili Desktop could not start.
echo Install Python 3.10+ for Windows with pip and the py launcher.
pause
exit /b 1
