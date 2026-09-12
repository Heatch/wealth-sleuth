@echo off
echo Starting Portfolio Tracker...
echo.

REM Kill existing processes on ports 8000 and 5173
echo Cleaning up existing processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo   Killing process %%a on port 8000
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo   Killing process %%a on port 5173
    taskkill /PID %%a /F >nul 2>&1
)

REM Wait for ports to be freed
timeout /t 2 /nobreak >nul

REM Start FastAPI backend (port 8000)
REM The API startup handler will:
REM   1. Check for new transaction files and consolidate if needed
REM   2. Detect price gaps and start background fetch
REM   3. Start live price refresh loop (every 15 min)
echo Starting API server on port 8000...
start "Portfolio API" cmd /c "cd /d "%~dp0" && venv\Scripts\python.exe -m uvicorn api.main:app --port 8000"

REM Wait for API to be ready (max ~2 min, then fail loudly)
echo Waiting for API to start...
set API_TRIES=0
:wait_api
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
  set /a API_TRIES+=1
  echo   ... still waiting ^(%API_TRIES%/60^)
  if %API_TRIES% GEQ 60 (
    echo ERROR: API did not start after 2 minutes.
    echo Check the "Portfolio API" window for errors.
    pause
    exit /b 1
  )
  goto wait_api
)
echo API is ready!

REM Start Vite frontend (port 5173)
echo Starting frontend on port 5173...
start "Portfolio Web" cmd /c "cd /d "%~dp0\web" && npm run dev"

REM Wait for Vite to be ready (max ~2 min, then fail loudly)
echo Waiting for frontend to start...
set WEB_TRIES=0
:wait_web
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:5173/ >nul 2>&1
if errorlevel 1 (
  set /a WEB_TRIES+=1
  echo   ... still waiting ^(%WEB_TRIES%/60^)
  if %WEB_TRIES% GEQ 60 (
    echo ERROR: Frontend did not start after 2 minutes.
    echo Check the "Portfolio Web" window for errors.
    pause
    exit /b 1
  )
  goto wait_web
)
echo Frontend is ready!

REM Open browser
echo Opening browser...
start http://127.0.0.1:5173

echo.
echo ========================================
echo Portfolio Tracker started!
echo   API:  http://127.0.0.1:8000
echo   Web:  http://127.0.0.1:5173
echo ========================================
echo.
echo The API will automatically:
echo   - Consolidate new transaction files (if any changed)
echo   - Fetch missing price data in background
echo   - Refresh live prices every 15 minutes
echo.
echo Close the "Portfolio API" and "Portfolio Web" windows to stop.
pause
