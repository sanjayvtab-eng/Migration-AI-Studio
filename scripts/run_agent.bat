@echo off
setlocal enabledelayedexpansion
title Databricks Migration AI Studio - Local Agent
echo ======================================================================
echo       Databricks Migration AI Studio - Local Agent Launcher
echo ======================================================================
echo.

if exist "%~dp0migration-agent.exe" (
    echo Running standalone executable: migration-agent.exe
    "%~dp0migration-agent.exe" %*
) else (
    echo Running with local Python interpreter...
    python "%~dp0local_connector.py" %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Agent stopped with exit code %ERRORLEVEL%.
    pause
)
