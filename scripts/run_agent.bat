@echo off
setlocal enabledelayedexpansion
title Databricks Migration AI Studio - Universal Local Agent
echo ======================================================================
echo       Databricks Migration AI Studio - Universal Local Agent
echo ======================================================================
echo.

if exist "%~dp0migration-agent.exe" (
    echo Running standalone executable: migration-agent.exe
    "%~dp0migration-agent.exe" %*
) else if exist "%~dp0..\backend\.venv\Scripts\python.exe" (
    echo Running with virtual environment Python interpreter...
    "%~dp0..\backend\.venv\Scripts\python.exe" "%~dp0local_connector.py" %*
) else (
    echo Running with system Python interpreter...
    python "%~dp0local_connector.py" %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Agent stopped with exit code %ERRORLEVEL%.
    pause
)
