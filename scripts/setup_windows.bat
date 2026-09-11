@echo off
setlocal
cd /d "%~dp0.."
echo [1/4] Preparing root configuration...
if not exist ".env" copy ".env.example" ".env" >nul
echo [2/4] Preparing Python 3.12 virtual environment...
cd backend
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
cd ..\frontend
echo [3/4] Installing frontend dependencies...
if not exist ".env" echo VITE_API_URL=http://127.0.0.1:8010/api>.env
call npm install
if errorlevel 1 exit /b 1
cd ..
echo [4/4] Setup complete.
echo Edit .env, then run scripts\bootstrap_admin.py and scripts\run_all_windows.bat
endlocal
