@echo off
setlocal
cd /d "%~dp0"

title Audio Subtitle Electron Workbench
echo Starting Electron workbench...
echo.

set "WORK_ROOT=%cd%\.runtime"
set "LOCAL_TMP=%WORK_ROOT%\.tmp"
set "LOCAL_CACHE=%WORK_ROOT%\.cache"

for %%I in ("%cd%") do set "APP_DIR_NAME=%%~nxI"
for %%I in ("%cd%\..") do set "APP_PARENT_DIR=%%~fI"
set "APP_RUNTIME_ROOT=%APP_PARENT_DIR%\%APP_DIR_NAME%_runtime"
if not exist "%APP_RUNTIME_ROOT%" set "APP_RUNTIME_ROOT=%WORK_ROOT%"

if not exist "%WORK_ROOT%" mkdir "%WORK_ROOT%" >nul 2>nul
if not exist "%LOCAL_TMP%" mkdir "%LOCAL_TMP%" >nul 2>nul
if not exist "%LOCAL_CACHE%" mkdir "%LOCAL_CACHE%" >nul 2>nul
if not exist "%APP_RUNTIME_ROOT%" mkdir "%APP_RUNTIME_ROOT%" >nul 2>nul

set "TEMP=%LOCAL_TMP%"
set "TMP=%LOCAL_TMP%"
set "HF_HOME=%LOCAL_CACHE%\huggingface"
set "XDG_CACHE_HOME=%LOCAL_CACHE%"
set "PIP_CACHE_DIR=%LOCAL_CACHE%\pip"
set "APP_RUNTIME_ROOT=%APP_RUNTIME_ROOT%"
set "ELECTRON_RUN_AS_NODE="

if defined CONDA_PREFIX (
    set "CONDA_SITE_PACKAGES=%CONDA_PREFIX%\Lib\site-packages"
    if not defined BACKEND_PYTHON if exist "%CONDA_PREFIX%\python.exe" set "BACKEND_PYTHON=%CONDA_PREFIX%\python.exe"
    if exist "%CONDA_SITE_PACKAGES%\PySide6" (
        set "PATH=%CONDA_SITE_PACKAGES%\PySide6;%CONDA_SITE_PACKAGES%\shiboken6;%CONDA_PREFIX%\Library\bin;%PATH%"
    )
)

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js was not found.
    echo Please install Node.js 18+ and make sure node / npm are available in PATH.
    echo.
    pause
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo npm.cmd was not found.
    echo Please repair the Node.js installation and try again.
    echo.
    pause
    exit /b 1
)

if not exist "package.json" (
    echo package.json was not found in the project root.
    echo.
    pause
    exit /b 1
)

if not exist "node_modules\electron" (
    echo Electron dependencies are not installed yet.
    echo Run: npm install
    echo Then start this launcher again.
    echo.
    pause
    exit /b 1
)

call npm.cmd run start
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Electron exited with error code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
