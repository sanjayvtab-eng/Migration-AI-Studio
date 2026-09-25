"""Build script to create the Standalone Single Executable (migration-agent.exe)
and distribution bundle for Databricks Migration AI Studio Local Connector.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def build():
    root = Path(__file__).resolve().parents[1]
    scripts_dir = root / "scripts"
    dist_dir = root / "dist"
    build_dir = root / "build"
    dist_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("Building Databricks Migration AI Studio - Standalone Agent")
    print("=" * 60)

    # 1. Run PyInstaller
    local_connector_py = scripts_dir / "local_connector.py"
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name", "migration-agent",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        str(local_connector_py)
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode != 0:
        print("[Warning] PyInstaller build returned non-zero code. Checking outputs...")
    else:
        print("[OK] PyInstaller build completed successfully.")

    exe_path = dist_dir / "migration-agent.exe"

    # 2. Build Universal Distribution ZIP Bundle
    zip_path = dist_dir / "migration-agent-bundle.zip"
    print(f"Creating distribution bundle: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if exe_path.is_file():
            z.write(exe_path, "migration-agent.exe")
            print("  Added migration-agent.exe")
        if local_connector_py.is_file():
            z.write(local_connector_py, "local_connector.py")
            print("  Added local_connector.py")
        bat_path = scripts_dir / "run_agent.bat"
        if bat_path.is_file():
            z.write(bat_path, "run_agent.bat")
            print("  Added run_agent.bat")
        env_example = scripts_dir / "agent.env.example"
        if env_example.is_file():
            z.write(env_example, "agent.env.example")
            z.write(env_example, "agent.env")
            print("  Added agent.env")
        reqs = scripts_dir / "connector-requirements.txt"
        if reqs.is_file():
            z.write(reqs, "requirements.txt")
            print("  Added requirements.txt")

        readme = (
            "======================================================================\n"
            "   Databricks Migration AI Studio - Standalone Local Agent\n"
            "======================================================================\n\n"
            "Quick Start (Windows):\n"
            "----------------------\n"
            "1. Open 'agent.env' in Notepad and enter your CONNECTOR_TOKEN from Studio UI.\n"
            "2. Double-click 'migration-agent.exe' (or 'run_agent.bat').\n"
            "3. The agent will connect outward over HTTPS to Migration AI Studio.\n"
            "   No ports need to be opened on your firewall!\n\n"
            "Switching Databases:\n"
            "--------------------\n"
            "To migrate a different database on this server, simply change the\n"
            "CONNECTOR_DATABASE name in 'agent.env', or run:\n"
            "  migration-agent.exe --database NewDatabaseName\n\n"
            "Python Runner (Alternative):\n"
            "----------------------------\n"
            "If not using the .exe, run:\n"
            "  pip install -r requirements.txt\n"
            "  python local_connector.py\n"
        )
        z.writestr("README.txt", readme)

    print("\n[SUCCESS] Standalone Agent and Distribution Bundle created in dist/")
    if exe_path.is_file():
        print(f"  Binary: {exe_path} ({exe_path.stat().st_size // (1024 * 1024)} MB)")
    print(f"  Bundle: {zip_path}")


if __name__ == "__main__":
    build()
