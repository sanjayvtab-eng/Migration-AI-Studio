@echo off
setlocal
set "URL=http://127.0.0.1:11434"
echo Testing Ollama at %URL% ...
curl -fsS %URL%/api/version
echo.
curl -fsS %URL%/api/tags
echo.
if errorlevel 1 (
  echo Ollama is not reachable. Run: ollama serve
  exit /b 1
)
echo Ollama is reachable.
endlocal
