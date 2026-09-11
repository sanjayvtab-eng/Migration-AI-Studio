@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
set ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
endlocal
