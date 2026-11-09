import json
import pathlib

import pytest

from core.extract import pdf_lines
from core.structure import blocks

scoring = pytest.importorskip("scoring")
run_rules = pytest.importorskip("run_rules")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = ROOT / "eval" / "rules.json"
FONT_INDEPENDENT = ["01", "02", "03", "04", "05", "06"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def generated():
    if not run_rules.MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")


def test_rules_cover_all_eight_samples_with_counts_only():
    samples = load(RULES)["samples"]
    assert sorted(samples) == [f"{n:02d}" for n in range(1, 9)]
    for record in samples.values():
        for name, value in record.items():
            if "percent" in value:
                expected = round(100 * value["found"] / value["of"], 1) if value["of"] else None
                assert value["percent"] == expected, name


def test_rules_are_reproduced_for_samples_that_do_not_depend_on_the_arabic_font():
    generated()
    fresh = run_rules.run()["samples"]
    committed = load(RULES)["samples"]
    for sample in FONT_INDEPENDENT:
        assert fresh[sample] == committed[sample], sample


def test_every_reference_anchor_is_in_its_sample():
    generated()
    for name, reference in load(run_rules.REFERENCE).items():
        _, lines = pdf_lines.read(run_rules.SAMPLES / "pdfs" / name)
        text = scoring.comparable(" ".join(line["text"] for line in blocks.restore_lines(lines)))
        for expected in reference["lists"]:
            assert scoring.comparable(expected["first_item"]) in text, (name, expected["first_item"])
        for expected in reference.get("headings", []):
            assert scoring.comparable(expected["text"]) in text, (name, expected["text"])
        for expected in reference["links"]:
            assert scoring.comparable(expected["text"]) in text, (name, expected["text"])
