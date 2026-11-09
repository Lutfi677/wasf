import argparse
import json
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any

import cu

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONFIG = ROOT / "config" / "azure.env"
SAMPLES = ROOT / "eval" / "samples" / "pdfs"
FIXTURES = ROOT / "eval" / "fixtures" / "cu"
RUNS = FIXTURES / "runs.json"
COST_LOG = ROOT / "eval" / "cost_log.jsonl"
DEFINITIONS = {
    "wasf_bakeoff_fields": HERE / "bakeoff_analyzer.json",
}
ANALYZERS = ("prebuilt-layout", "prebuilt-documentSearch", *DEFINITIONS)
RETRY_WAIT = 60
PHASE = "2 step 4"


def read_config(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def fixture_path(analyzer: str, sample: str) -> pathlib.Path:
    return FIXTURES / analyzer / f"{sample}.json"


def write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


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


def analyze_once_more_on_failure(client: Any, analyzer: str, data: bytes) -> tuple[dict[str, Any], dict[str, Any], float] | None:
    for attempt in (1, 2):
        try:
            return cu.analyze(client, analyzer, data)
        except Exception as error:
            print(f"  attempt {attempt} failed: {describe(error)}")
            if attempt == 1:
                time.sleep(RETRY_WAIT)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Content Understanding responses for the phase 2 bake-off")
    parser.add_argument("--sample", action="append", help="sample id such as 01; repeat for more; default all")
    parser.add_argument("--analyzer", action="append", choices=ANALYZERS, help="repeat for more; default all three")
    parser.add_argument("--refresh", action="store_true", help="call again even when a fixture exists")
    args = parser.parse_args()

    config = read_config(CONFIG)
    ceiling = int(config["CU_MAX_CALLS"])
    samples = sorted(path.name[:2] for path in SAMPLES.glob("*.pdf"))
    if args.sample:
        samples = [sample for sample in samples if sample in args.sample]
    analyzers = args.analyzer or list(ANALYZERS)
    pending = [(a, s) for a in analyzers for s in samples if args.refresh or not fixture_path(a, s).is_file()]
    if not pending:
        print("Nothing to record: every fixture exists. Use --refresh to call again.")
        return 0

    client = cu.make_client(config["CONTENTUNDERSTANDING_ENDPOINT"])
    wanted = sorted({a for a, _ in pending if a in DEFINITIONS})
    create = [a for a in wanted if not cu.analyzer_exists(client, a)]
    planned = len(pending) + len(create)
    if planned > ceiling:
        print(f"Refused: {planned} calls planned, ceiling CU_MAX_CALLS is {ceiling}")
        return 2
    print(f"{planned} live calls planned, ceiling {ceiling}")

    for analyzer in create:
        created = cu.create_analyzer(client, analyzer, json.loads(DEFINITIONS[analyzer].read_text(encoding="utf-8")))
        log_cost(analyzer, created.get("usage") or {}, f"phase {PHASE}; create analyzer")
        print(f"created analyzer {analyzer}: status {created.get('status')}")

    runs = json.loads(RUNS.read_text(encoding="utf-8")) if RUNS.is_file() else {"calls": {}}
    for analyzer, sample in pending:
        data = next(SAMPLES.glob(f"{sample}_*.pdf")).read_bytes()
        outcome = analyze_once_more_on_failure(client, analyzer, data)
        if outcome is None:
            print(f"Stopped at {analyzer} {sample} after one retry")
            return 1
        result, usage, seconds = outcome
        write_json(fixture_path(analyzer, sample), result)
        runs["calls"][f"{analyzer}/{sample}"] = {"recorded": now(), "seconds": round(seconds, 1), "usage": usage}
        runs["calls"] = dict(sorted(runs["calls"].items()))
        write_json(RUNS, runs)
        log_cost(analyzer, usage, f"phase {PHASE}; sample {sample}")
        print(f"{sample} {analyzer}: {seconds:.1f} s, pages {page_total(usage)}, "
              f"input {token_total(usage, 'input')}, output {token_total(usage, 'output')}, "
              f"contextualization {usage.get('contextualizationTokens')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
