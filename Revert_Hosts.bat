@echo off
:: Revert Hosts File — removes little-prince.com.hk and sunnyinteractive.com entries
:: Run as administrator (right-click → Run as administrator)

echo.
echo  Reverting hosts file...
echo.

:: Self-elevate to admin if not already
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set HOSTS=%SystemRoot%\System32\drivers\etc\hosts

:: Backup first
copy /y "%HOSTS%" "%HOSTS%.bak" >nul 2>&1
echo  Backup saved to: %HOSTS%.bak

:: Remove the four lines
powershell -Command "(Get-Content '%HOSTS%') | Where-Object { $_ -notmatch 'little-prince\.com\.hk|www\.little-prince|sunnyinteractive\.com|file\.sunnyinteractive' } | Set-Content '%HOSTS%'"

:: Flush DNS
ipconfig /flushdns >nul 2>&1

echo.
echo  Done! Hosts file cleaned. You can now access the official website.
echo.
pause
