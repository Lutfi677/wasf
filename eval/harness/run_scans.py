import json
import pathlib
import sys
from collections import Counter
from typing import Any

import scoring

from core.scan import crosscheck, line_rule
from core.scan.lines import Line, service_lines, tesseract_lines

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REFERENCE = HERE / "scan_reference.json"
TESSERACT = ROOT / "eval" / "fixtures" / "tesseract"
SERVICE = ROOT / "eval" / "fixtures" / "cu" / "prebuilt-layout"
SCANS = ROOT / "eval" / "scans.json"


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def lines_of(sample: str) -> tuple[dict[str, Any], list[Line], list[Line]]:
    recorded = load(TESSERACT / f"{sample}.json")
    scanned = {page["number"] for page in recorded["pages"]}
    first = [line for page in recorded["pages"] for line in tesseract_lines(page)]
    second = [line for line in service_lines(load(SERVICE / f"{sample}.json")) if line["page"] in scanned]
    return recorded, first, second


def line_counts(lines: list[Line]) -> dict[str, int]:
    return {"lines": len(lines), "flagged": sum(1 for line in lines if line_rule.goes_to_person(line))}


def score_sample(sample: str, reference: dict[str, Any]) -> dict[str, Any]:
    _, first, second = lines_of(sample)
    regions = crosscheck.route(first, second)
    record: dict[str, Any] = {
        "lines": {"tesseract": line_counts(first), "service": line_counts(second)},
        "reasons": dict(sorted(Counter(reason for region in regions for reason in region["reasons"]).items())),
    }
    if reference.get("parcel_lines"):
        record.update(scoring.parcel_scores(reference["parcel_lines"], regions, first + second))
    return record


def run() -> dict[str, Any]:
    reference = load(REFERENCE)
    samples: dict[str, Any] = {}
    versions: set[str] = set()
    for path in sorted(TESSERACT.glob("*.json")):
        recorded, _, _ = lines_of(path.stem)
        versions.add(f"tesseract {recorded['version']}")
        samples[path.stem] = score_sample(path.stem, reference.get(path.stem, {}))
    return {
        "engine": "wasf-scan with " + ", ".join(sorted(versions)) + " and prebuilt-layout",
        "rule": {"average_minimum": line_rule.AVERAGE_MINIMUM, "word_minimum": line_rule.WORD_MINIMUM},
        "samples": samples,
    }


def main() -> int:
    if not any(TESSERACT.glob("*.json")):
        print("No Tesseract fixtures. Run: python -m providers.local.record_tesseract")
        return 2
    scans = run()
    SCANS.write_text(json.dumps(scans, indent=2) + "\n", encoding="utf-8", newline="\n")
    for sample, record in scans["samples"].items():
        shown = " ".join(f"{name}={value['percent']}" for name, value in record.items() if isinstance(value, dict) and "percent" in value)
        print(sample, shown, f"confidently_wrong={record.get('confidently_wrong')}", record["lines"], record["reasons"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
