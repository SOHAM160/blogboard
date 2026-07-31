@echo off
REM ============================================================
REM  setup_daily_task.bat
REM  Creates a Windows Task Scheduler task to auto-generate
REM  BlogBoard articles daily at 6:00 AM IST.
REM  
REM  Run this ONCE as Administrator to set up the task.
REM ============================================================

set PROJECT_DIR=%~dp0
set PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe
set SCRIPT=%PROJECT_DIR%daily_auto_generate.py
set TASK_NAME=BlogBoard_Daily_Generator

echo.
echo =========================================================
echo   BlogBoard - Setting up Daily Auto-Generation Task
echo =========================================================
echo.
echo   Project Dir : %PROJECT_DIR%
echo   Python      : %PYTHON_EXE%
echo   Script      : %SCRIPT%
echo   Task Name   : %TASK_NAME%
echo   Schedule    : Daily at 06:00 AM
echo.

REM Delete existing task if it exists
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM Create the scheduled task
schtasks /Create ^
  /TN "%TASK_NAME%" ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT%\"" ^
  /SC DAILY ^
  /ST 06:00 ^
  /RL HIGHEST ^
  /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo   ✅ Task created successfully!
    echo   Articles will be generated daily at 6:00 AM.
    echo   Logs will be saved in: %PROJECT_DIR%logs\
    echo.
    echo   To verify: Open Task Scheduler and look for "%TASK_NAME%"
    echo   To run now: schtasks /Run /TN "%TASK_NAME%"
    echo   To delete:  schtasks /Delete /TN "%TASK_NAME%" /F
    echo.
) else (
    echo.
    echo   ❌ Failed to create task. Try running as Administrator.
    echo.
)

pause
