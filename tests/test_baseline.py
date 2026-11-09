import json
import pathlib

import pytest

scoring = pytest.importorskip("scoring")
extractors = pytest.importorskip("offline_extractors")

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "eval" / "baseline.json"
TARGETS = ROOT / "eval" / "targets.json"
ANCHORS = ROOT / "eval" / "harness" / "order_anchors.json"
EXCLUSIONS = ROOT / "eval" / "harness" / "text_exclusions.json"
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
TOOLS = {"pdfminer.six", "pypdfium2", "pdftotext"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def manifest():
    if not MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")
    return load(MANIFEST)


def test_baseline_covers_eight_samples_and_three_tools():
    baseline = load(BASELINE)
    assert set(baseline["tools"]) == TOOLS
    assert sorted(baseline["samples"]) == [f"{n:02d}" for n in range(1, 9)]
    for by_tool in baseline["samples"].values():
        assert set(by_tool) == TOOLS


def test_baseline_percents_match_their_counts():
    for by_tool in load(BASELINE)["samples"].values():
        for scores in by_tool.values():
            for count in scores.values():
                expected = round(100 * count["found"] / count["of"], 1) if count["of"] else None
                assert count["percent"] == expected


def test_targets_follow_the_rule_from_the_committed_baseline():
    assert load(TARGETS) == scoring.targets(load(BASELINE))


def test_fixed_targets_are_present():
    samples = load(TARGETS)["samples"]
    assert samples["01"]["header_cells"] == {"target": 100, "from": "fixed"}
    assert samples["02"]["header_cells"] == {"target": 100, "from": "fixed"}
    assert samples["05"]["parcel_lines_to_person"] == {"target": 100, "from": "fixed"}


def test_committed_files_hold_no_answer_key_text():
    committed = BASELINE.read_text(encoding="utf-8").casefold() + TARGETS.read_text(encoding="utf-8").casefold()
    for entry in manifest()["documents"]:
        for text in scoring.key_strings(entry):
            if len(text) >= 5:
                assert text not in committed


def test_anchor_file_follows_the_answer_key_order():
    anchors = load(ANCHORS)
    by_name = {pathlib.PurePosixPath(entry["file"]).name: entry for entry in manifest()["documents"]}
    for name, items in anchors.items():
        assert [item["key"] for item in items] == by_name[name]["expected_reading_order"]
    assert set(anchors) == {name for name, entry in by_name.items() if "expected_reading_order" in entry}


def test_every_exclusion_is_a_key_string_of_its_sample():
    by_name = {pathlib.PurePosixPath(entry["file"]).name: entry for entry in manifest()["documents"]}
    for name, excluded in load(EXCLUSIONS).items():
        strings = scoring.key_strings(by_name[name])
        kept = scoring.key_strings(by_name[name], excluded)
        assert len(strings) - len(kept) == len(excluded)


@pytest.mark.parametrize("tool", ["pdfminer.six", "pypdfium2"])
def test_python_extractors_return_ordered_blocks_inside_the_page(tool):
    manifest()
    result = extractors.EXTRACTORS[tool](SAMPLES / "pdfs" / "01_county_budget_summary.pdf")
    assert result["engine"] == tool
    assert [page["number"] for page in result["pages"]] == [1, 2, 3]
    assert [block["reading_order"] for block in result["blocks"]] == list(range(len(result["blocks"])))
    sizes = {page["number"]: (page["width"], page["height"]) for page in result["pages"]}
    for block in result["blocks"]:
        assert block["text"].strip()
        assert block["role"] is None
        left, top, right, bottom = block["box"]
        width, height = sizes[block["page"]]
        assert -1 <= left <= right <= width + 1
        assert -1 <= top <= bottom <= height + 1


def test_pdftotext_returns_blocks_when_poppler_is_installed():
    manifest()
    try:
        extractors.find_pdftotext()
    except extractors.ToolMissing as error:
        pytest.skip(str(error))
    result = extractors.pdftotext_result(SAMPLES / "pdfs" / "01_county_budget_summary.pdf")
    assert result["version"].startswith("poppler ")
    assert len(result["pages"]) == 3
    assert result["blocks"]


def test_scan_gives_no_text_layer():
    manifest()
    result = extractors.pdfminer_result(SAMPLES / "pdfs" / "05_planning_notice_fax_scan.pdf")
    assert len(result["pages"]) == 2
    assert result["blocks"] == []
