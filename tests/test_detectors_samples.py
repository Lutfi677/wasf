import json
import os
import pathlib

import pikepdf
import pytest

from core.detectors import RULE_IDS, detect

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "eval" / "samples"
MANIFEST = SAMPLES / "answer_key" / "manifest.json"
AFTER = SAMPLES / "pdfs_after"
METADATA_IDS = {"NO_TAGS", "NO_TITLE", "BAD_TITLE", "NO_LANG"}
SEEDED_TOTAL = 31
EXPECTED_EXTRAS = {
    "02_college_fee_schedule.pdf": {"LOW_CONTRAST"},
    "04_council_minutes_with_pii.pdf": {"LOW_CONTRAST"},
    "06_library_report_injection_fixture.pdf": {"LOW_CONTRAST"},
    "07_arabic_circular_two_column.pdf": {"LOW_CONTRAST"},
}


def require_samples():
    if MANIFEST.is_file() and AFTER.is_dir():
        return
    if os.environ.get("CI"):
        pytest.fail("eval/samples or eval/samples/pdfs_after is missing in CI")
    pytest.skip("eval/samples has not been generated: run make_samples.py and make_after.py in eval/samples_tools")


@pytest.fixture(scope="module")
def documents():
    require_samples()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [(pathlib.PurePosixPath(entry["file"]).name, SAMPLES / entry["file"], entry) for entry in manifest["documents"]]


@pytest.fixture(scope="module")
def originals(documents):
    results = {}
    for name, path, entry in documents:
        seeded = {item["id"] for item in entry["seeded_defects"]} & set(RULE_IDS)
        results[name] = (seeded, path, detect(path))
    return results


def test_every_original_finds_its_seeded_rules_and_the_pinned_extras(originals):
    mismatches = {}
    for name, (seeded, _, findings) in originals.items():
        expected = seeded | EXPECTED_EXTRAS.get(name, set())
        found = {finding.defect for finding in findings}
        if found != expected:
            mismatches[name] = {"missed": sorted(expected - found), "unexpected": sorted(found - expected)}
    assert mismatches == {}


def test_31_of_31_seeded_defects_are_found(originals):
    seeded_total = sum(len(seeded) for seeded, _, _ in originals.values())
    seeded_found = sum(len(seeded & {finding.defect for finding in findings}) for seeded, _, findings in originals.values())
    assert (seeded_found, seeded_total) == (SEEDED_TOTAL, SEEDED_TOTAL)


def test_findings_point_at_pages_inside_the_file(originals):
    for _, path, findings in originals.values():
        with pikepdf.open(path) as pdf:
            pages = len(pdf.pages)
        assert all(finding.page is None or 1 <= finding.page <= pages for finding in findings)


def test_after_copies_have_none_of_the_four_metadata_types(documents):
    leftovers = {}
    for name, _, _ in documents:
        path = AFTER / name
        assert path.is_file(), f"pdfs_after/{name} is missing"
        found = {finding.defect for finding in detect(path)} & METADATA_IDS
        if found:
            leftovers[name] = sorted(found)
    assert leftovers == {}
