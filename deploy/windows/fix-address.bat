@echo off
setlocal
rem Day Pay HRMS - double-click after the server IP changed ("Bad Request (400)"). Windows asks for administrator rights.
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
    echo Asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%* ' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix-address.ps1" %*
echo.
pause
