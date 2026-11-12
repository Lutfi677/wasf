import argparse
import itertools
import json
import pathlib
import sys
from typing import Any, cast

import scoring

from core.extract.shapes import Result
from core.model import assemble as assembly
from core.model.document import Document
from providers.azure.cu_provider import ContentUnderstandingProvider
from providers.local.own import LocalProvider
from providers.recorded.recorded import RecordedProvider, recorded_scan_lines

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
ANCHORS = HERE / "order_anchors.json"
EXCLUSIONS = HERE / "text_exclusions.json"
REFERENCE = HERE / "structure_reference.json"
SCAN_REFERENCE = HERE / "scan_reference.json"
TARGETS = ROOT / "eval" / "targets.json"
MODEL = ROOT / "eval" / "model.json"
LIVE = ROOT / "eval" / "fixtures" / "live"
MODEL_LIVE = ROOT / "eval" / "model_live.json"


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_result(document: Document) -> Result:
    return cast(Result, document.model_dump())


def parcel_lines_routed(parcel_lines: list[dict[str, Any]], document: Document) -> scoring.Count:
    sizes = {page.number: page for page in document.pages}
    routed = 0
    for line in parcel_lines:
        for region in document.regions:
            page = sizes[region.page]
            left, top, right, bottom = region.box
            fractions = [left / page.width, top / page.height, right / page.width, bottom / page.height]
            if scoring.on_reference(line, region.page, fractions):
                routed += 1
                break
    return {"found": routed, "of": len(parcel_lines)}


def score_sample(
    entry: dict[str, Any],
    document: Document,
    service: Result,
    anchors: list[dict[str, Any]] | None,
    excluded: list[str] | None,
    reference: dict[str, Any],
    parcel_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    result = as_result(document)
    scores: dict[str, scoring.Count] = {"text": scoring.text_score(entry, result, excluded)}
    if anchors:
        scores["reading_order"] = scoring.reading_order_score(anchors, result)
    expected = entry.get("headings_expected") or reference.get("headings") or []
    if expected:
        scores["headings"], _ = scoring.heading_scores(expected, result)
    tables = scoring.table_scores(entry, result)
    if tables is not None:
        scores["table_cells"], scores["header_cells"] = tables
    if parcel_lines:
        scores["parcel_lines_to_person"] = parcel_lines_routed(parcel_lines, document)
    record: dict[str, Any] = {metric: scoring.with_percent(count) for metric, count in scores.items()}
    wanted = scoring.primary_language(entry.get("language_expected"))
    if wanted is not None:
        record["language"] = {"expected": wanted, "found": document.language, "right": document.language == wanted}
    record["counts"] = {
        "blocks": len(document.blocks),
        "tables": len(document.tables),
        "links": len(document.links),
        "figures": len(document.figures),
        "regions": len(document.regions),
        "unmatched_service_headings": assembly.unmatched_service_headings(document, service),
    }
    return record


def gate(samples: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for sample, metrics in targets["samples"].items():
        for metric, target in metrics.items():
            value = samples[sample].get(metric, {}).get("percent")
            met = value is not None and value >= target["target"]
            rows[f"{sample}/{metric}"] = {"target": target["target"], "value": value, "met": met}
    open_rows = [name for name, row in rows.items() if not row["met"]]
    return {"met": len(rows) - len(open_rows), "of": len(rows), "open": open_rows, "rows": rows}


def differences(live: Document, recorded: Document) -> dict[str, int]:
    def unequal(first: list[Any], second: list[Any]) -> int:
        return sum(1 for a, b in itertools.zip_longest(first, second) if a != b)

    return {
        "blocks": unequal(live.blocks, recorded.blocks),
        "tables": unequal(live.tables, recorded.tables),
        "figures": unequal(live.figures, recorded.figures),
        "regions": unequal(live.regions, recorded.regions),
    }


def inputs() -> dict[str, Any]:
    return {
        "anchors": load(ANCHORS),
        "exclusions": load(EXCLUSIONS),
        "references": load(REFERENCE),
        "scan_references": load(SCAN_REFERENCE),
        "targets": load(TARGETS),
    }


def sample_inputs(entry: dict[str, Any], given: dict[str, Any]) -> tuple[str, pathlib.Path, dict[str, Any]]:
    name = pathlib.PurePosixPath(entry["file"]).name
    scoring_inputs = {
        "anchors": given["anchors"].get(name),
        "excluded": given["exclusions"].get(name),
        "reference": given["references"].get(name, {}),
        "parcel_lines": given["scan_references"].get(name[:2], {}).get("parcel_lines", []),
    }
    return name[:2], SAMPLES / entry["file"], scoring_inputs


def run() -> dict[str, Any]:
    given = inputs()
    recorded = RecordedProvider()
    local = LocalProvider(recorded_scan_lines)
    samples: dict[str, Any] = {}
    for entry in load(MANIFEST)["documents"]:
        sample, pdf, extra = sample_inputs(entry, given)
        service = recorded.read(pdf)
        document = assembly.assemble(service, local.read(pdf))
        samples[sample] = score_sample(entry, document, service, **extra)
    return {"samples": samples, "gate": gate(samples, given["targets"])}


def run_live() -> dict[str, Any]:
    given = inputs()
    recorded = RecordedProvider()
    local = LocalProvider(recorded_scan_lines)
    samples: dict[str, Any] = {}
    for entry in load(MANIFEST)["documents"]:
        sample, pdf, extra = sample_inputs(entry, given)
        kept = LIVE / f"{sample}.json"
        if not kept.is_file():
            continue
        response = load(kept)
        live_provider = ContentUnderstandingProvider(lambda _data, response=response: (response, {}, 0.0))
        local_result = local.read(pdf)
        live_service = live_provider.read(pdf)
        recorded_service = recorded.read(pdf)
        live_document = assembly.assemble(live_service, local_result)
        recorded_document = assembly.assemble(recorded_service, local_result)
        live_scores = score_sample(entry, live_document, live_service, **extra)
        recorded_scores = score_sample(entry, recorded_document, recorded_service, **extra)
        samples[sample] = {
            "validates": True,
            "identical": live_document == recorded_document,
            "metrics_equal": live_scores == recorded_scores,
            "differences": differences(live_document, recorded_document),
        }
    return {"analyzer": "prebuilt-layout", "samples": samples}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the document model for every sample and score it")
    parser.add_argument("--live", action="store_true", help="build from the kept live responses and compare with the recorded ones")
    args = parser.parse_args()
    if not MANIFEST.is_file():
        print("eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
        return 2
    if args.live:
        live = run_live()
        if not live["samples"]:
            print("No kept live responses. Run: python -m providers.azure.check_live")
            return 2
        MODEL_LIVE.write_text(json.dumps(live, indent=2) + "\n", encoding="utf-8", newline="\n")
        for sample, record in live["samples"].items():
            print(sample, record)
        return 0
    model = run()
    MODEL.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    for sample, record in model["samples"].items():
        shown = " ".join(f"{k}={v['percent']}" for k, v in record.items() if isinstance(v, dict) and "percent" in v)
        print(sample, shown, record.get("language", ""), record["counts"])
    print("gate", model["gate"]["met"], "of", model["gate"]["of"], "met; open:", model["gate"]["open"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
