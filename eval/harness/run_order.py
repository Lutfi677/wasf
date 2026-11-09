import json
import pathlib
import sys
from typing import Any

import cu_convert
import offline_extractors
import scoring

from core.extract.shapes import Result
from core.order import xy_cut
from core.structure import blocks

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
ANCHORS = HERE / "order_anchors.json"
EXCLUSIONS = HERE / "text_exclusions.json"
REFERENCE = HERE / "structure_reference.json"
FIXTURES = ROOT / "eval" / "fixtures" / "cu"
TARGETS = ROOT / "eval" / "targets.json"
ORDER = ROOT / "eval" / "order.json"
SERVICE = "prebuilt-layout"
NO_FORMULA = "wasf_layout_noformula"
DONE_WHEN = ("03", "07")


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def service(analyzer: str, sample: str) -> Result | None:
    path = FIXTURES / analyzer / f"{sample}.json"
    return cu_convert.fold_arabic(cu_convert.convert(load(path), analyzer)) if path.is_file() else None


def own(path: pathlib.Path) -> Result:
    result = blocks.structure(path)
    result["blocks"] = xy_cut.order(result["blocks"])
    return result


def score_sample(
    entry: dict[str, Any], anchors: list[dict[str, Any]] | None, excluded: list[str] | None, reference: dict[str, Any]
) -> dict[str, Any]:
    sample = pathlib.PurePosixPath(entry["file"]).name[:2]
    pdf = SAMPLES / entry["file"]
    own_result = own(pdf)
    service_result = service(SERVICE, sample)
    sources: dict[str, Result | None] = {
        "own": own_result,
        "service": service_result,
        "service_noformula": service(NO_FORMULA, sample),
        "stream": offline_extractors.pypdfium2_result(pdf),
    }
    record: dict[str, Any] = {}
    for name, result in sources.items():
        if result is None:
            continue
        scores: dict[str, scoring.Count] = {"text": scoring.text_score(entry, result, excluded)}
        if anchors:
            scores["reading_order"] = scoring.reading_order_score(anchors, result)
        if "source_text_logical_order" in entry:
            scores["units"], scores["mixed_units"] = scoring.unit_scores(entry["source_text_logical_order"], result)
        tables = scoring.table_scores(entry, result)
        if tables is not None:
            scores["table_strings"] = scoring.table_strings(entry, result)
            if name.startswith("service"):
                scores["table_cells"], scores["header_cells"] = tables
        expected = entry.get("headings_expected") or reference.get("headings") or []
        if expected:
            scores["headings"], _ = scoring.heading_scores(expected, result)
        if reference.get("lists") and name == "own":
            scores["lists"], scores["list_items"] = scoring.list_scores(reference["lists"], result)
        record[name] = {metric: scoring.with_percent(count) for metric, count in scores.items()}
    expected = entry.get("headings_expected") or reference.get("headings") or []
    if expected and service_result is not None:
        pairs = zip(scoring.headings_found(expected, own_result), scoring.headings_found(expected, service_result), strict=True)
        either = [a or b for a, b in pairs]
        record["own_or_service"] = {"headings": scoring.with_percent({"found": sum(either), "of": len(either)})}
    return record


def best(record: dict[str, Any], metric: str, names: tuple[str, ...]) -> tuple[float | None, str | None]:
    found = [
        (record[name][metric]["percent"], -rank, name)
        for rank, name in enumerate(names)
        if name in record and metric in record[name] and record[name][metric]["percent"] is not None
    ]
    if not found:
        return None, None
    value, _, name = max(found)
    return value, name


def targets_met(sample: str, record: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    sources = {
        "text": ("own", "service"),
        "reading_order": ("own",),
        "headings": ("own_or_service",),
        "table_cells": ("service", "service_noformula"),
        "header_cells": ("service", "service_noformula"),
    }
    met: dict[str, Any] = {}
    for metric, target in targets["samples"][sample].items():
        if metric not in sources:
            continue
        value, source = best(record, metric, sources[metric])
        met[metric] = {"target": target["target"], "value": value, "source": source, "met": value is not None and value >= target["target"]}
    return met


def run() -> dict[str, Any]:
    anchors = load(ANCHORS)
    exclusions = load(EXCLUSIONS)
    references = load(REFERENCE)
    targets = load(TARGETS)
    samples: dict[str, Any] = {}
    for entry in load(MANIFEST)["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        samples[name[:2]] = score_sample(entry, anchors.get(name), exclusions.get(name), references.get(name, {}))
    return {"samples": samples, "done_when": {sample: targets_met(sample, samples[sample], targets) for sample in DONE_WHEN}}


def main() -> int:
    if not MANIFEST.is_file():
        print("eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
        return 2
    order = run()
    ORDER.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8", newline="\n")
    for sample, record in order["samples"].items():
        for name, scores in record.items():
            print(sample, name, " ".join(f"{metric}={count['percent']}" for metric, count in scores.items()))
    for sample, met in order["done_when"].items():
        print("done-when", sample, {metric: (m["value"], m["target"], m["source"], m["met"]) for metric, m in met.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
