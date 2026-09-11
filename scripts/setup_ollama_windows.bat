@echo off
setlocal
cd /d "%~dp0.."
set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=qwen2.5-coder:3b"

echo [1/5] Checking Ollama installation...
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed or is not on PATH.
  echo Install Ollama for Windows first, then rerun this script.
  exit /b 1
)
ollama --version

echo [2/5] Checking local Ollama service...
curl -fsS http://127.0.0.1:11434/api/tags >nul 2>nul
if errorlevel 1 (
  echo Ollama service is not responding. Starting ollama serve in a new window...
  start "Ollama Service" cmd /k "ollama serve"
  timeout /t 3 /nobreak >nul
)

echo [3/5] Pulling model %MODEL% ...
ollama pull %MODEL%
if errorlevel 1 exit /b 1

echo [4/5] Configuring Migration Factory .env ...
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" scripts\configure_ollama.py --model "%MODEL%"
) else (
  python scripts\configure_ollama.py --model "%MODEL%"
)
if errorlevel 1 exit /b 1

echo [5/5] Verifying Ollama models...
curl -fsS http://127.0.0.1:11434/api/tags

echo.
echo Local Ollama setup is complete.
echo Restart the Migration Factory backend, open AI Remediation, and click Test Ollama.
endlocal
