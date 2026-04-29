@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

set "BACKEND_HOST=127.0.0.1"
if defined SHAFA_BACKEND_HOST set "BACKEND_HOST=%SHAFA_BACKEND_HOST%"

set "BACKEND_PORT=8000"
if defined SHAFA_BACKEND_PORT set "BACKEND_PORT=%SHAFA_BACKEND_PORT%"
set "FRONTEND_PORT=5173"

set "API_BASE_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"
set "SHAFA_API_BASE_URL=%API_BASE_URL%"
set "VENV_ACTIVATE="
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "HIDDEN_RUNNER=%SCRIPT_DIR%run-hidden.vbs"
set "LOG_DIR=%PROJECT_ROOT%\runtime\windows-dev-logs"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"

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

if not exist "%HIDDEN_RUNNER%" (
  echo Hidden runner not found: %HIDDEN_RUNNER%
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
break > "%BACKEND_LOG%"
break > "%FRONTEND_LOG%"

echo Releasing dev ports if needed...
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%

:start_backend
echo Starting backend in background...
wscript //nologo "%HIDDEN_RUNNER%" "cmd.exe /c cd /d ""%PROJECT_ROOT%"" && set SHAFA_BACKEND_HOST=%BACKEND_HOST% && set SHAFA_BACKEND_PORT=%BACKEND_PORT% && ""%PYTHON_EXE%"" %PYTHON_ARGS% desktop_backend.py >> ""%BACKEND_LOG%"" 2>&1"

echo Waiting for backend to become ready...
call :wait_for_backend
if errorlevel 1 exit /b 1

:start_frontend
echo Starting frontend in background...
wscript //nologo "%HIDDEN_RUNNER%" "cmd.exe /c cd /d ""%PROJECT_ROOT%\desktop-ui"" && npm run dev >> ""%FRONTEND_LOG%"" 2>&1"

echo Backend and frontend were started in background.
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
echo See backend log: %BACKEND_LOG%
exit /b 1

:kill_port
set "TARGET_PORT=%~1"
if "%TARGET_PORT%"=="" exit /b 0

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
  if not "%%P"=="0" (
    echo Stopping process %%P on port %TARGET_PORT%...
    taskkill /PID %%P /F >nul 2>nul
  )
)

exit /b 0
