@echo off
setlocal
cd /d "%~dp0"

title Audio Subtitle Tool
echo Starting audio subtitle tool...
echo This run will clear old files in input and output first.
echo.
set "KMP_DUPLICATE_LIB_OK=TRUE"

set "PY_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PY_CMD=python"

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Please install Python and add it to PATH.
    echo.
    pause
    exit /b 1
)

call %PY_CMD% main.py
set "EXIT_CODE=%errorlevel%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo Program exited with error code %EXIT_CODE%.
) else (
    echo Done.
)

pause
exit /b %EXIT_CODE%
