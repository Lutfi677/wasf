import json
import pathlib
import sys
from typing import Any

import scoring
from offline_extractors import EXTRACTORS, ToolMissing

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
ANCHORS = HERE / "order_anchors.json"
EXCLUSIONS = HERE / "text_exclusions.json"
BASELINE = ROOT / "eval" / "baseline.json"
TARGETS = ROOT / "eval" / "targets.json"


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def run() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))
    exclusions = json.loads(EXCLUSIONS.read_text(encoding="utf-8"))
    tools: dict[str, str] = {}
    samples: dict[str, dict[str, Any]] = {}
    for entry in manifest["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        for tool, extract in EXTRACTORS.items():
            result = extract(SAMPLES / entry["file"])
            tools[tool] = result["version"]
            scores = scoring.score(entry, result, anchors.get(name), exclusions.get(name))
            samples.setdefault(name[:2], {})[tool] = {metric: scoring.with_percent(count) for metric, count in scores.items()}
    return {"tools": tools, "samples": samples}


def main() -> int:
    if not MANIFEST.is_file():
        print("eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
        return 2
    try:
        baseline = run()
    except ToolMissing as error:
        print(error)
        return 2
    write_json(BASELINE, baseline)
    write_json(TARGETS, scoring.targets(baseline))
    for sample, by_tool in baseline["samples"].items():
        for tool, scores in by_tool.items():
            print(sample, tool, " ".join(f"{metric}={count['percent']}" for metric, count in scores.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
