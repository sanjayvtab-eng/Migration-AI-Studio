from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

DEFAULTS = {
    "LLM_ENABLED": "true",
    "LLM_PROVIDER": "OLLAMA",
    "LLM_BASE_URL": "http://127.0.0.1:11434",
    "LLM_API_KEY": "",
    "LLM_MODEL": "qwen2.5-coder:3b",
    "LLM_TIMEOUT_SECONDS": "120",
    "LLM_MAX_ATTEMPTS": "3",
    "LLM_NUM_CTX": "8192",
    "LLM_NUM_PREDICT": "4096",
    "LLM_MAX_PROMPT_CHARS": "160000",
    "OLLAMA_KEEP_ALIVE": "5m",
}


def update_env(path: Path, values: dict[str, str]) -> None:
    if not path.exists():
        if not EXAMPLE.exists():
            raise SystemExit(".env.example not found")
        shutil.copy2(EXAMPLE, path)
    backup = path.with_name(f".env.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(path, backup)
    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    out: list[str] = []
    managed = set(values)
    emitted: set[str] = set()
    for line in lines:
        stripped = line.strip()
        candidate = stripped[1:].strip() if stripped.startswith("#") else stripped
        key = candidate.split("=", 1)[0].strip() if "=" in candidate else ""
        if key in managed:
            # Remove duplicate/commented managed settings and emit exactly one active value.
            if key not in emitted:
                out.append(f"{key}={values[key]}")
                emitted.add(key)
                remaining.pop(key, None)
            continue
        out.append(line)
    if remaining:
        out.append("")
        out.append("# Local Ollama AI configuration")
        out.extend(f"{k}={v}" for k, v in remaining.items())
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"Updated: {path}")
    print(f"Backup : {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Migration Factory to use local Ollama")
    parser.add_argument("--model", default=DEFAULTS["LLM_MODEL"], help="Installed Ollama model name")
    parser.add_argument("--base-url", default=DEFAULTS["LLM_BASE_URL"], help="Ollama base URL")
    args = parser.parse_args()
    values = dict(DEFAULTS)
    values["LLM_MODEL"] = args.model
    values["LLM_BASE_URL"] = args.base_url.rstrip("/")
    update_env(ENV, values)
    print("\nOllama AI is enabled in .env.")
    print("Restart the Migration Factory backend so settings are reloaded.")


if __name__ == "__main__":
    main()
