from __future__ import annotations

import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config" / "azure.env"

def load() -> None:
    if not CONFIG.exists():
        return
    for raw in CONFIG.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def require(*names: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"Missing setting(s): {', '.join(missing)}.\n"
            f"Add them to {CONFIG}."
        )
