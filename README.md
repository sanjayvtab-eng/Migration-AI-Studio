# SQL Server → Databricks AI Migration Factory — 2.2.0 DYNAMIC_COMPATIBILITY_FRAMEWORK

**Build marker:** the UI must display `Build 2.2.0 DYNAMIC_COMPATIBILITY_FRAMEWORK`. If you do not see that marker, you are running an older extracted folder or browser/Vite instance.

## Windows quick start
1. Copy `.env.example` to `.env` and configure SQL Server/Databricks values.
2. Run `scripts\run_backend.bat`. Backend: `http://127.0.0.1:8010`; Swagger: `http://127.0.0.1:8010/docs`.
3. In another terminal run `scripts\run_frontend.bat`. Frontend: Vite prints `http://localhost:5173` or `5174`.
4. Create the first administrator with `python scripts\bootstrap_admin.py` from the project root.

## Project source

This repository was initialized from the approved `Databricks_Migration` main branch at commit `f537494`. The remaining application files are uploaded in the next source commit.
