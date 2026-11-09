import json
import pathlib
import sys
from typing import Any

import cu_convert
import scoring

from core.extract import pdf_lines
from core.structure import blocks

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
REFERENCE = HERE / "structure_reference.json"
LAYOUT = ROOT / "eval" / "fixtures" / "cu" / "prebuilt-layout"
RULES = ROOT / "eval" / "rules.json"


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def agreement(rules: list[bool], service: list[bool]) -> dict[str, int]:
    pairs = list(zip(rules, service, strict=True))
    return {
        "both": sum(1 for a, b in pairs if a and b),
        "rules_only": sum(1 for a, b in pairs if a and not b),
        "service_only": sum(1 for a, b in pairs if b and not a),
        "neither": sum(1 for a, b in pairs if not a and not b),
    }


def score_sample(entry: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    sample = pathlib.PurePosixPath(entry["file"]).name[:2]
    result = blocks.structure(SAMPLES / entry["file"])
    scores: dict[str, scoring.Count] = {}
    expected = entry.get("headings_expected") or reference.get("headings") or []
    if expected:
        scores["headings"], scores["heading_precision"] = scoring.heading_scores(expected, result)
    if reference.get("lists"):
        scores["lists"], scores["list_items"] = scoring.list_scores(reference["lists"], result)
    if reference.get("links"):
        scores["links"] = scoring.link_scores(reference["links"], result)
    record: dict[str, Any] = {metric: scoring.with_percent(count) for metric, count in scores.items()}
    if expected:
        service = cu_convert.fold_arabic(cu_convert.convert(load(LAYOUT / f"{sample}.json"), "prebuilt-layout"))
        record["heading_agreement"] = agreement(scoring.headings_found(expected, result), scoring.headings_found(expected, service))
    record["counts"] = {
        "blocks": len(result["blocks"]),
        "headings": sum(1 for block in result["blocks"] if block["role"] == "heading"),
        "list_items": sum(1 for block in result["blocks"] if block["role"] == "listItem"),
        "links": len(result.get("links") or []),
    }
    return record


def run() -> dict[str, Any]:
    reference = load(REFERENCE)
    samples: dict[str, Any] = {}
    for entry in load(MANIFEST)["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        samples[name[:2]] = score_sample(entry, reference.get(name, {}))
    return {"engine": f"{blocks.ENGINE} on {pdf_lines.version()}", "samples": samples}


def main() -> int:
    if not MANIFEST.is_file():
        print("eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
        return 2
    rules = run()
    RULES.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8", newline="\n")
    for sample, record in rules["samples"].items():
        shown = " ".join(f"{metric}={value['percent']}" for metric, value in record.items() if "percent" in value)
        print(sample, shown, record.get("heading_agreement", ""), record["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
