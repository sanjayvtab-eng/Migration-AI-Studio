from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

EXCLUDED_DIRS = {".git", ".venv", ".review-venv", "node_modules", "dist", "build", "bin", "__pycache__", ".pytest_cache", "review-output"}
EXCLUDED_FILES = {".env", "migration_factory.db", "migration_factory.sqlite", "migration_factory.sqlite3"}
def main() -> None:
    parser = argparse.ArgumentParser(description="Create a clean Migration AI Studio source release")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_dir() or any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.name == 'agent.env':
            continue
        if relative.parts[0] == 'remediation' and (path.suffix.lower() == '.xml' or path.name == 'full-progress.json'):
            continue
        if path.name in EXCLUDED_FILES or path.suffix.lower() in {".db", ".pyc", ".exe", ".zip", ".log"}:
            continue
        if path.resolve() == output:
            continue
        files.append(path)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("Migration-AI-Studio") / path.relative_to(root))
    print(f"Created {output} with {len(files)} files")


if __name__ == "__main__":
    main()
