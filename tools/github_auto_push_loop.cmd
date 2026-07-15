@echo off
setlocal EnableExtensions
set "AUTODIR=%LOCALAPPDATA%\WindMailMonitor\AutoPush"
set "LOGFILE=%AUTODIR%\github-auto-push.log"
set "REPOFILE=%AUTODIR%\repo_path.txt"
set "DISABLEFILE=%AUTODIR%\disabled.flag"

if not exist "%AUTODIR%" mkdir "%AUTODIR%" >nul 2>&1
if not exist "%REPOFILE%" exit /b 1
set /p "REPO="<"%REPOFILE%"
if not defined REPO exit /b 1

:loop
if exist "%DISABLEFILE%" exit /b 0
set "BRANCH="
for /f "usebackq delims=" %%B in (`git -C "%REPO%" branch --show-current 2^>nul`) do set "BRANCH=%%B"
if /i "%BRANCH%"=="main" (
    >>"%LOGFILE%" echo [%date% %time%] Checking origin/main...
    git -C "%REPO%" pull --rebase origin main >>"%LOGFILE%" 2>&1
    if errorlevel 1 (
        >>"%LOGFILE%" echo [%date% %time%] ERROR: git pull --rebase failed. Push skipped.
    ) else (
        git -C "%REPO%" push origin main >>"%LOGFILE%" 2>&1
        if errorlevel 1 >>"%LOGFILE%" echo [%date% %time%] ERROR: git push failed.
    )
) else (
    >>"%LOGFILE%" echo [%date% %time%] Skipped: current branch is not main.
)
timeout /t 300 /nobreak >nul
goto loop
