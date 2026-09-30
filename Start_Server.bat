@echo off
title Prince 3-in-1 Server
cd /d "%~dp0"

echo.
echo   Starting local server on port 80...
echo   While it runs, the official game domains point at this PC.
echo   Stop it with Ctrl+C - or simply close this window - and the hosts
echo   file is reverted automatically. Revert_Hosts.bat is only a fallback
echo   for the case where this process is force-killed.
echo.

net session >nul 2>&1
if not errorlevel 1 goto :start

echo   Requesting admin rights...
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:start
set "PRINCE_PID="
python fake_server.py
call :revert
echo.
echo   Server stopped.
pause
exit /b 0

:revert
net session >nul 2>&1
if errorlevel 1 exit /b 0
set "HOSTS=%SystemRoot%\System32\drivers\etc\hosts"
powershell -NoProfile -Command "(Get-Content '%HOSTS%') | Where-Object { $_ -notmatch 'little-prince\.com\.hk|www\.little-prince|sunnyinteractive\.com|file\.sunnyinteractive' } | Set-Content '%HOSTS%'"
ipconfig /flushdns >nul 2>&1
echo   hosts file reverted - normal web browsing restored.
exit /b 0
