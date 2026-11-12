import json
import pathlib
import re

import pytest

run_scans = pytest.importorskip("run_scans")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANS = ROOT / "eval" / "scans.json"
TARGETS = ROOT / "eval" / "targets.json"
FIXTURE = ROOT / "eval" / "fixtures" / "tesseract" / "05.json"
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def key_entry():
    if not MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")
    return next(entry for entry in load(MANIFEST)["documents"] if entry["file"].endswith("05_planning_notice_fax_scan.pdf"))


def test_committed_scans_match_the_recorded_fixtures():
    assert load(SCANS) == run_scans.run()


def test_two_runs_give_the_same_scans():
    assert run_scans.run() == run_scans.run()


def test_done_when_the_three_parcel_lines_go_to_a_person_and_none_is_confidently_wrong():
    record = load(SCANS)["samples"]["05"]
    target = load(TARGETS)["samples"]["05"]["parcel_lines_to_person"]["target"]
    assert record["parcel_lines_to_person"]["of"] == 3
    assert record["parcel_lines_to_person"]["percent"] >= target
    assert record["confidently_wrong"] == 0


def test_the_service_alone_misses_a_parcel_line_that_the_cross_check_catches():
    record = load(SCANS)["samples"]["05"]
    assert record["line_rule_alone"]["service"]["found"] < record["parcel_lines_to_person"]["found"]


def test_every_wrong_reading_sits_on_a_routed_line():
    record = load(SCANS)["samples"]["05"]
    assert max(record["read_wrong"].values()) > 0
    assert record["confidently_wrong"] == 0


def test_scans_hold_no_answer_key_text():
    key = key_entry()
    committed = SCANS.read_text(encoding="utf-8").casefold()
    for text in key["expected_low_confidence"][0]["true_text"]:
        assert text.casefold() not in committed
        assert re.findall(r"\d+-\d+-\d+", text)[0] not in committed


def test_reference_follows_the_answer_key():
    key = key_entry()
    reference = load(run_scans.REFERENCE)["05"]["parcel_lines"]
    numbers = [re.sub(r"\D", "", re.findall(r"\d+-\d+-\d+", text)[0]) for text in key["expected_low_confidence"][0]["true_text"]]
    assert [line["parcel_digits"] for line in reference] == numbers


def test_live_tesseract_reproduces_the_recorded_words_when_installed():
    pytest.importorskip("pytesseract")
    import pypdfium2

    from providers.local import tesseract

    key_entry()
    try:
        version = tesseract.configure()
    except tesseract.ToolMissing as error:
        pytest.skip(str(error))
    fixture = load(FIXTURE)
    if version != fixture["version"]:
        pytest.skip(f"tesseract {version} differs from the recorded {fixture['version']}")
    document = pypdfium2.PdfDocument(str(SAMPLES / "pdfs" / "05_planning_notice_fax_scan.pdf"))
    try:
        image = tesseract.render(document[0])
    finally:
        document.close()
    data = tesseract.recognise(image)
    assert data["text"] == fixture["pages"][0]["data"]["text"]
    assert data["conf"] == fixture["pages"][0]["data"]["conf"]
