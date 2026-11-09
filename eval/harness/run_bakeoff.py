import json
import pathlib
import sys
from typing import Any

import cu_convert
import scoring

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
ANCHORS = HERE / "order_anchors.json"
EXCLUSIONS = HERE / "text_exclusions.json"
FIXTURES = ROOT / "eval" / "fixtures" / "cu"
RUNS = FIXTURES / "runs.json"
BAKEOFF = ROOT / "eval" / "bakeoff.json"
CUSTOM = "wasf_bakeoff_fields"
ANALYZERS = ("prebuilt-layout", "prebuilt-documentSearch", CUSTOM)


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def usage_totals(calls: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for key, call in sorted(calls.items()):
        analyzer = key.split("/")[0]
        empty = {"calls": 0, "seconds": 0.0, "slowest_seconds": 0.0, "pages": 0, "contextualization_tokens": 0, "tokens": {}}
        total = totals.setdefault(analyzer, empty)
        usage = call["usage"]
        total["calls"] += 1
        total["seconds"] = round(total["seconds"] + call["seconds"], 1)
        total["slowest_seconds"] = max(total["slowest_seconds"], call["seconds"])
        total["pages"] += sum(usage.get(name) or 0 for name in ("documentPagesMinimal", "documentPagesBasic", "documentPagesStandard"))
        total["contextualization_tokens"] += usage.get("contextualizationTokens") or 0
        for name, count in sorted((usage.get("tokens") or {}).items()):
            total["tokens"][name] = total["tokens"].get(name, 0) + count
    return totals


def run() -> dict[str, Any]:
    manifest = load(MANIFEST)
    anchors = load(ANCHORS)
    exclusions = load(EXCLUSIONS)
    samples: dict[str, dict[str, Any]] = {}
    versions: dict[str, str] = {}
    for entry in manifest["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        sample = name[:2]
        for analyzer in ANALYZERS:
            response = load(FIXTURES / analyzer / f"{sample}.json")
            result = cu_convert.convert(response, analyzer)
            versions[analyzer] = result["version"]
            scores = scoring.score(entry, result, anchors.get(name), exclusions.get(name))
            if analyzer == CUSTOM:
                scores.update(scoring.field_scores(entry, cu_convert.fields(response)))
            samples.setdefault(sample, {})[analyzer] = {metric: scoring.with_percent(count) for metric, count in scores.items()}
    return {"analyzers": versions, "samples": samples, "usage": usage_totals(load(RUNS)["calls"])}


def main() -> int:
    if not MANIFEST.is_file():
        print("eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
        return 2
    bakeoff = run()
    BAKEOFF.write_text(json.dumps(bakeoff, indent=2) + "\n", encoding="utf-8", newline="\n")
    for sample, by_analyzer in bakeoff["samples"].items():
        for analyzer, scores in by_analyzer.items():
            print(sample, analyzer, " ".join(f"{metric}={count['percent']}" for metric, count in scores.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
