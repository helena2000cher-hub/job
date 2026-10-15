@echo off
rem Job Matcher: start locally with a double click. Opens http://localhost:8000
rem The server runs in a separate minimized window; stop it with stop.bat.
chcp 65001 >nul
cd /d "%~dp0"

if not exist backend\.venv\Scripts\python.exe (
  echo [!] Python environment not found. See README: "Quick start".
  pause
  exit /b 1
)

rem Already running? Just open the browser.
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  start "" http://localhost:8000
  exit /b 0
)

if not exist frontend\node_modules (
  echo Installing interface packages, first run only...
  pushd frontend
  call npm install --no-audit --no-fund || (popd & pause & exit /b 1)
  popd
)

echo Building interface...
pushd frontend
call npm run build >nul || (echo [!] Interface build failed & popd & pause & exit /b 1)
popd

start "Job Matcher server - do not close (use stop.bat)" /min backend\.venv\Scripts\python.exe -m uvicorn app.api.main:app --app-dir backend --host 127.0.0.1 --port 8000
if not "%1"=="--no-browser" (
  timeout /t 3 >nul
  start "" http://localhost:8000
)
