@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "BACKEND_HOST=127.0.0.1"
if defined SHAFA_BACKEND_HOST set "BACKEND_HOST=%SHAFA_BACKEND_HOST%"

set "BACKEND_PORT=8000"
if defined SHAFA_BACKEND_PORT set "BACKEND_PORT=%SHAFA_BACKEND_PORT%"

set "API_BASE_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"
set "SHAFA_API_BASE_URL=%API_BASE_URL%"
set "VENV_ACTIVATE="
set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%PROJECT_ROOT%\venv\Scripts\activate.bat" (
  set "VENV_ACTIVATE=%PROJECT_ROOT%\venv\Scripts\activate.bat"
) else (
  if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    set "VENV_ACTIVATE=%PROJECT_ROOT%\.venv\Scripts\activate.bat"
  )
)

if defined SHAFA_PYTHON (
  set "PYTHON_EXE=%SHAFA_PYTHON%"
) else (
  if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
  ) else (
    if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
      set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    )
  )
)

if not defined PYTHON_EXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
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
call :check_backend
if errorlevel 1 goto start_backend

echo Reusing running backend at %API_BASE_URL%
goto start_frontend

:start_backend
echo Starting backend in a new window...
if defined VENV_ACTIVATE (
  start "Shafa Backend" cmd /k "cd /d ""%PROJECT_ROOT%"" && call ""%VENV_ACTIVATE%"" && python -m uvicorn telegram_accounts_api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"
) else (
  start "Shafa Backend" cmd /k "cd /d ""%PROJECT_ROOT%"" && ""%PYTHON_EXE%"" %PYTHON_ARGS% -m uvicorn telegram_accounts_api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"
)

echo Waiting for backend to become ready...
call :wait_for_backend
if errorlevel 1 exit /b 1

:start_frontend
echo Starting frontend in a new window...
start "Shafa Frontend" cmd /k "cd /d ""%PROJECT_ROOT%\desktop-ui"" && npm run dev"

echo Backend and frontend launch commands were started.
exit /b 0

:check_backend
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen(sys.argv[1], timeout=2).status == 200 else 1)" "%API_BASE_URL%/health" >nul 2>nul
exit /b %errorlevel%

:wait_for_backend
for /L %%N in (1,1,60) do (
  call :check_backend
  if not errorlevel 1 exit /b 0
  >nul timeout /t 1 /nobreak
)

echo Backend did not become ready at %API_BASE_URL%/health
exit /b 1
