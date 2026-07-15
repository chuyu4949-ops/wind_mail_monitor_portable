@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "AUTODIR=%LOCALAPPDATA%\WindMailMonitor\AutoPush"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\WindMailMonitor_GitHubAutoPush.vbs"

if not exist "%AUTODIR%" mkdir "%AUTODIR%" >nul 2>&1
if errorlevel 1 goto :failed

copy /y "%~dp0tools\github_auto_push_loop.cmd" "%AUTODIR%\github_auto_push_loop.cmd" >nul
if errorlevel 1 goto :failed
copy /y "%~dp0tools\github_auto_push_launcher.vbs" "%LAUNCHER%" >nul
if errorlevel 1 goto :failed

>"%AUTODIR%\repo_path.txt" echo %~dp0
del /q "%AUTODIR%\disabled.flag" >nul 2>&1

start "" wscript.exe "%LAUNCHER%"
git -C "%~dp0" push origin main

echo.
echo Installed successfully.
echo Auto-push runs every 5 minutes while this Windows user is logged in.
echo Log: %AUTODIR%\github-auto-push.log
pause
exit /b 0

:failed
echo.
echo Install failed. Please check access to the current user's Startup folder.
pause
exit /b 1
