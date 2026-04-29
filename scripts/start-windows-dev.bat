@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "BACKEND_HOST=127.0.0.1"
if not "%SHAFA_BACKEND_HOST%"=="" set "BACKEND_HOST=%SHAFA_BACKEND_HOST%"

set "BACKEND_PORT=8000"
if not "%SHAFA_BACKEND_PORT%"=="" set "BACKEND_PORT=%SHAFA_BACKEND_PORT%"

set "API_BASE_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"
set "SHAFA_API_BASE_URL=%API_BASE_URL%"
set "VENV_ACTIVATE="

if exist "%PROJECT_ROOT%\venv\Scripts\activate.bat" (
  set "VENV_ACTIVATE=%PROJECT_ROOT%\venv\Scripts\activate.bat"
) else if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
  set "VENV_ACTIVATE=%PROJECT_ROOT%\.venv\Scripts\activate.bat"
)

set "PYTHON_EXE="
set "PYTHON_ARGS="
if defined SHAFA_PYTHON (
  set "PYTHON_EXE=%SHAFA_PYTHON%"
) else if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
  set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
) else if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 (
      set "PYTHON_EXE=python"
    )
  )
)

if not defined PYTHON_EXE (
  echo Python not found. Create .venv/venv or set SHAFA_PYTHON.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm not found. Install Node.js first.
  exit /b 1
)

echo Checking backend at %API_BASE_URL%/health
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing '%API_BASE_URL%/health' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"

if errorlevel 1 (
  echo Starting backend in a new window...
  if defined VENV_ACTIVATE (
    start "Shafa Backend" cmd /k "cd /d \"%PROJECT_ROOT%\" && call \"%VENV_ACTIVATE%\" && \"%PYTHON_EXE%\" %PYTHON_ARGS% -m uvicorn telegram_accounts_api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"
  ) else (
    start "Shafa Backend" cmd /k "cd /d \"%PROJECT_ROOT%\" && \"%PYTHON_EXE%\" %PYTHON_ARGS% -m uvicorn telegram_accounts_api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"
  )

  echo Waiting for backend to become ready...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline=(Get-Date).AddSeconds(60);" ^
    "while((Get-Date) -lt $deadline) {" ^
    "  try {" ^
    "    $r = Invoke-WebRequest -UseBasicParsing '%API_BASE_URL%/health' -TimeoutSec 2;" ^
    "    if ($r.StatusCode -lt 500) { exit 0 }" ^
    "  } catch {}" ^
    "  Start-Sleep -Seconds 1;" ^
    "}" ^
    "Write-Error 'Backend did not become ready in time.'; exit 1"

  if errorlevel 1 exit /b 1
) else (
  echo Reusing running backend at %API_BASE_URL%
)

echo Starting frontend in a new window...
start "Shafa Frontend" cmd /k "cd /d \"%PROJECT_ROOT%\desktop-ui\" && npm run dev"

echo Backend and frontend launch commands were started.
exit /b 0
