@echo off
setlocal
cd /d "%~dp0"

title Audio Subtitle GUI
echo Starting desktop GUI...
echo.

set "LOCAL_PY312=C:\Users\zzz\AppData\Local\Programs\Python\Python312\python.exe"
set "BACKEND_PYTHON=C:\Users\zzz\anaconda3\python.exe"
set "RUNTIME_ROOT=%cd%_runtime"
set "ANACONDA_SITE_PACKAGES=C:\Users\zzz\anaconda3\Lib\site-packages"
set "LOCAL_TMP=%RUNTIME_ROOT%\.tmp"
set "LOCAL_CACHE=%RUNTIME_ROOT%\.cache"

if not exist "%LOCAL_TMP%" mkdir "%LOCAL_TMP%" >nul 2>nul
if not exist "%LOCAL_CACHE%" mkdir "%LOCAL_CACHE%" >nul 2>nul
if not exist "%RUNTIME_ROOT%" mkdir "%RUNTIME_ROOT%" >nul 2>nul

set "TEMP=%LOCAL_TMP%"
set "TMP=%LOCAL_TMP%"
set "HF_HOME=%LOCAL_CACHE%\huggingface"
set "XDG_CACHE_HOME=%LOCAL_CACHE%"
set "PIP_CACHE_DIR=%LOCAL_CACHE%\pip"
set "APP_RUNTIME_ROOT=%RUNTIME_ROOT%"
set "PYTHONPATH=%ANACONDA_SITE_PACKAGES%;%cd%"
set "PATH=%ANACONDA_SITE_PACKAGES%\PySide6;%ANACONDA_SITE_PACKAGES%\shiboken6;C:\Users\zzz\anaconda3\Library\bin;%PATH%"
set "BACKEND_PYTHON=%BACKEND_PYTHON%"

set "PY_CMD="
if exist "%LOCAL_PY312%" if exist "%ANACONDA_SITE_PACKAGES%\PySide6" set "PY_CMD=%LOCAL_PY312%"

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Please install Python and add it to PATH.
    echo.
    pause
    exit /b 1
)

if /i "%PY_CMD%"=="python" (
    call python gui.py
) else if /i "%PY_CMD%"=="py -3" (
    call py -3 gui.py
) else (
    call "%PY_CMD%" gui.py
)
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo GUI exited with error code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
