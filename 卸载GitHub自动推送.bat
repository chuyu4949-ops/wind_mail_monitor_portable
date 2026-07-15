@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "AUTODIR=%LOCALAPPDATA%\WindMailMonitor\AutoPush"
set "LAUNCHER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\WindMailMonitor_GitHubAutoPush.vbs"

if not exist "%AUTODIR%" mkdir "%AUTODIR%" >nul 2>&1
type nul >"%AUTODIR%\disabled.flag"
del /q "%LAUNCHER%" >nul 2>&1

echo Auto-push has been disabled.
echo The background process will exit within 5 minutes.
pause
