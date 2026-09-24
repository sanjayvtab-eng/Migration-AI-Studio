@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Backend virtual environment not found. Run setup_windows.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m compileall -q app tests
python -m pytest -q
endlocal
