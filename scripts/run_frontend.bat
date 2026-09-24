@echo off
setlocal
cd /d "%~dp0..\frontend"
if not exist ".env" echo VITE_API_URL=http://127.0.0.1:8010/api>.env
if not exist "node_modules" npm install
npm run dev
endlocal
