@echo off
REM ============================================================
REM Last War Kill Tracker - Windows Task Scheduler Setup
REM Creates TWO scheduled tasks:
REM   1. Daily at 02:55 - Capture kill data
REM   2. Weekly on Sunday at 03:05 - Generate weekly summary
REM ============================================================

echo ============================================
echo  Last War Kill Tracker - Scheduler Setup
echo ============================================
echo.

REM Get the directory of this script
set SCRIPT_DIR=%~dp0

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Get the full Python path
for /f "tokens=*" %%i in ('where python') do (
    set PYTHON_PATH=%%i
    goto :found_python
)
:found_python

echo Python found at: %PYTHON_PATH%
echo Script directory: %SCRIPT_DIR%
echo.

REM ---- Task 1: Daily capture at 02:55 ----
echo [1/2] Creating daily task "LastWarKillTracker"...
echo       Schedule: Every day at 02:55
echo.

schtasks /create ^
    /tn "LastWarKillTracker" ^
    /tr "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%main.py\"" ^
    /sc daily ^
    /st 02:55 ^
    /rl HIGHEST ^
    /f

if %ERRORLEVEL% equ 0 (
    echo       [OK] Daily task created successfully!
) else (
    echo       [FAIL] Could not create daily task.
)
echo.

REM ---- Task 2: Weekly summary on Sunday at 03:05 ----
echo [2/2] Creating weekly task "LastWarWeeklySummary"...
echo       Schedule: Every Sunday at 03:05
echo.

schtasks /create ^
    /tn "LastWarWeeklySummary" ^
    /tr "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%main.py\" --skip-launch --weekly-summary" ^
    /sc weekly ^
    /d SUN ^
    /st 03:05 ^
    /rl HIGHEST ^
    /f

if %ERRORLEVEL% equ 0 (
    echo       [OK] Weekly summary task created successfully!
) else (
    echo       [FAIL] Could not create weekly task.
)

echo.
echo ============================================
echo  Setup Complete!
echo ============================================
echo.
echo  Daily:  02:55 - Capture kill data
echo  Sunday: 03:05 - Generate weekly summary
echo.
echo IMPORTANT NOTES:
echo  - Make sure your PC is awake at these times
echo  - Run calibrate.py first to set up navigation
echo.
echo To remove tasks later:
echo   schtasks /delete /tn "LastWarKillTracker" /f
echo   schtasks /delete /tn "LastWarWeeklySummary" /f
echo.

pause
