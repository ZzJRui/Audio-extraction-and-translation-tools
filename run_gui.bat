@echo off
setlocal
cd /d "%~dp0"

title Audio Subtitle GUI
echo Starting desktop GUI...
echo.

set "RUNTIME_ROOT=%cd%_runtime"
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

if defined CONDA_PREFIX (
    set "CONDA_SITE_PACKAGES=%CONDA_PREFIX%\Lib\site-packages"
    if exist "%CONDA_SITE_PACKAGES%\PySide6" (
        set "PYTHONPATH=%CONDA_SITE_PACKAGES%;%cd%"
        set "PATH=%CONDA_SITE_PACKAGES%\PySide6;%CONDA_SITE_PACKAGES%\shiboken6;%CONDA_PREFIX%\Library\bin;%PATH%"
    )
    if not defined BACKEND_PYTHON if exist "%CONDA_PREFIX%\python.exe" set "BACKEND_PYTHON=%CONDA_PREFIX%\python.exe"
)

set "PY_CMD="
if defined GUI_PYTHON if exist "%GUI_PYTHON%" set "PY_CMD=%GUI_PYTHON%"

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
