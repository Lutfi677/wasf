import json
import pathlib
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config" / "azure.env"
COST_LOG = ROOT / "eval" / "cost_log.jsonl"


def read_config(path: pathlib.Path = CONFIG) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def token_total(usage: dict[str, Any], kind: str) -> int | None:
    tokens = usage.get("tokens") or {}
    found = [count for name, count in tokens.items() if name.endswith(f"-{kind}")]
    return sum(found) if found else None


def page_total(usage: dict[str, Any]) -> int:
    return sum(usage.get(name) or 0 for name in ("documentPagesMinimal", "documentPagesBasic", "documentPagesStandard"))


def log_cost(analyzer: str, usage: dict[str, Any], note: str) -> None:
    row = {
        "timestamp": now(),
        "phase": 2,
        "service": "content-understanding",
        "deployment": analyzer,
        "input_tokens": token_total(usage, "input"),
        "output_tokens": token_total(usage, "output"),
        "pages": page_total(usage),
        "note": f"{note}; usage={json.dumps(usage, sort_keys=True)}",
    }
    with COST_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def describe(error: Exception) -> str:
    status = getattr(error, "status_code", None)
    code = getattr(getattr(error, "error", None), "code", None)
    return f"{type(error).__name__} status={status} code={code}"
