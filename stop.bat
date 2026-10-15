@echo off
rem Job Matcher: stop the local server started by start.bat
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c[0].OwningProcess -Force; 'Job Matcher stopped.' } else { 'Job Matcher is not running.' }"
timeout /t 2 >nul
