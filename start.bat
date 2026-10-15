@echo off
rem Job Matcher: start locally with a double click. Opens http://localhost:8000
rem Close this window to stop the site.
chcp 65001 >nul
cd /d "%~dp0"
title Job Matcher

if not exist backend\.venv\Scripts\python.exe (
  echo [!] Python environment not found. See README: "Quick start".
  pause
  exit /b 1
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

if not "%1"=="--no-browser" start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"

echo.
echo   Job Matcher: http://localhost:8000
echo   To stop, close this window.
echo.
backend\.venv\Scripts\python.exe -m uvicorn app.api.main:app --app-dir backend --host 127.0.0.1 --port 8000
