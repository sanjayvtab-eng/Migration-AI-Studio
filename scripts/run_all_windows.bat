@echo off
start "Migration Factory Backend" cmd /k "%~dp0run_backend.bat"
start "Migration Factory Frontend" cmd /k "%~dp0run_frontend.bat"
