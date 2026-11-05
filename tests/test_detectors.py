import logging

import pytest
from pdf_builder import build, line

from core.detectors import detect
from core.detectors.contrast import contrast_ratio, detect_contrast
from core.detectors.links import detect_links, is_vague_link_text
from core.detectors.metadata import detect_metadata, is_bad_title
from core.detectors.scan import detect_image_only
from core.findings import Source, State

FULL_PAGE_IMAGE = b"q 612 0 0 792 0 0 cm /Im0 Do Q\n"


def defects(findings):
    return [finding.defect for finding in findings]


def test_black_on_white_is_21_to_1():
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255)), 2) == 21.0


def test_contrast_ratio_does_not_depend_on_order():
    assert contrast_ratio((10, 80, 120), (240, 240, 200)) == contrast_ratio((240, 240, 200), (10, 80, 120))


def test_equal_colours_give_1_to_1():
    assert round(contrast_ratio((120, 120, 120), (120, 120, 120)), 2) == 1.0


def test_bare_file_has_no_tags_title_or_language(tmp_path):
    assert defects(detect_metadata(build(tmp_path))) == ["NO_TAGS", "NO_TITLE", "NO_LANG"]


def test_tagged_titled_file_with_language_passes(tmp_path):
    path = build(tmp_path, title="Service Request Form", lang="en", marked=True, tree=True)
    assert detect_metadata(path) == []


@pytest.mark.parametrize("halves", [{"marked": True}, {"tree": True}])
def test_one_half_of_tagging_is_not_enough(tmp_path, halves):
    path = build(tmp_path, title="Service Request Form", lang="en", **halves)
    assert defects(detect_metadata(path)) == ["NO_TAGS"]


def test_xmp_title_is_used_when_info_has_none(tmp_path):
    path = build(tmp_path, xmp_title="Service Request Form", lang="en", marked=True, tree=True)
    assert detect_metadata(path) == []


@pytest.mark.parametrize("title", ["Microsoft Word - Minutes 03-12-26 DRAFT.doc", "form_v2.indd", "Document1", "Untitled", "report.pdf"])
def test_file_names_and_defaults_are_bad_titles(tmp_path, title):
    assert is_bad_title(title)
    findings = detect_metadata(build(tmp_path, title=title, lang="en", marked=True, tree=True))
    assert defects(findings) == ["BAD_TITLE"]
    assert title in findings[0].evidence


@pytest.mark.parametrize("title", ["City Council Regular Meeting Minutes, March 12, 2026", "Service Request Form"])
def test_real_titles_are_not_bad_titles(tmp_path, title):
    assert not is_bad_title(title)
    assert detect_metadata(build(tmp_path, title=title, lang="en", marked=True, tree=True)) == []


@pytest.mark.parametrize("lang", ["", "   "])
def test_blank_language_is_no_language(tmp_path, lang):
    path = build(tmp_path, title="Service Request Form", lang=lang, marked=True, tree=True)
    assert defects(detect_metadata(path)) == ["NO_LANG"]


def test_arabic_language_passes(tmp_path):
    assert detect_metadata(build(tmp_path, title="Circular", lang="ar", marked=True, tree=True)) == []


def test_grey_text_on_white_is_low_contrast(tmp_path):
    findings = detect_contrast(build(tmp_path, line("Page 2 of 4", grey=150)))
    assert defects(findings) == ["LOW_CONTRAST"]
    assert findings[0].page == 1
    assert "1 text run is below" in findings[0].evidence


def test_black_text_on_white_passes(tmp_path):
    assert detect_contrast(build(tmp_path, line("Page 2 of 4"))) == []


def test_large_text_needs_only_3_to_1(tmp_path):
    assert detect_contrast(build(tmp_path, line("Notice", size=24, grey=137))) == []
    findings = detect_contrast(build(tmp_path, line("Notice", size=12, grey=137), name="small.pdf"))
    assert defects(findings) == ["LOW_CONTRAST"]
    assert "4.5:1 is needed" in findings[0].evidence


def test_low_contrast_is_one_finding_per_page(tmp_path):
    stream = line("Footer one", grey=150) + line("Footer two", grey=176, y=650)
    findings = detect_contrast(build(tmp_path, stream))
    assert defects(findings) == ["LOW_CONTRAST"]
    assert "2 text runs are below" in findings[0].evidence


@pytest.mark.parametrize("text", ["click here", "Click here.", "here", "Read more"])
def test_vague_link_text(text):
    assert is_vague_link_text(text)


def test_descriptive_link_text_is_not_vague():
    assert not is_vague_link_text("Download the 2026 budget summary")


def test_vague_link_is_found(tmp_path):
    findings = detect_links(build(tmp_path, line("click here"), links=[(68, 694, 140, 714)]))
    assert defects(findings) == ["VAGUE_LINK"]
    assert findings[0].page == 1
    assert "'click here'" in findings[0].evidence


def test_descriptive_link_passes(tmp_path):
    assert detect_links(build(tmp_path, line("Download the 2026 budget summary"), links=[(68, 694, 300, 714)])) == []


def test_raw_url_is_found(tmp_path):
    findings = detect_links(build(tmp_path, line("or visit https://www.example.org/welcome.")))
    assert defects(findings) == ["RAW_URL"]
    assert "'https://www.example.org/welcome'" in findings[0].evidence


def test_url_under_a_link_passes(tmp_path):
    assert detect_links(build(tmp_path, line("or visit https://www.example.org/welcome."), links=[(60, 690, 400, 715)])) == []


def test_full_page_image_with_no_text_is_image_only(tmp_path):
    findings = detect_image_only(build(tmp_path, FULL_PAGE_IMAGE))
    assert defects(findings) == ["IMAGE_ONLY"]
    assert findings[0].page == 1
    assert "100%" in findings[0].evidence


def test_image_with_text_is_not_image_only(tmp_path):
    assert detect_image_only(build(tmp_path, FULL_PAGE_IMAGE + line("Parcel record"))) == []


def test_blank_page_is_not_image_only(tmp_path):
    assert detect_image_only(build(tmp_path)) == []


def test_detect_returns_unreviewed_rule_findings_in_order(tmp_path):
    stream = line("click here", grey=150) + line("or visit https://www.example.org/welcome.", y=650)
    findings = detect(build(tmp_path, stream, title="Document1", links=[(68, 694, 140, 714)]))
    assert defects(findings) == ["NO_TAGS", "BAD_TITLE", "NO_LANG", "LOW_CONTRAST", "VAGUE_LINK", "RAW_URL"]
    assert [finding.page for finding in findings] == [None, None, None, 1, 1, 1]
    for finding in findings:
        assert finding.source is Source.rule
        assert finding.state is State.proposed
        assert finding.proposed_fix is None


def test_detectors_log_nothing(tmp_path, caplog):
    path = build(tmp_path, line("click here", grey=150), title="Document1", links=[(68, 694, 140, 714)])
    with caplog.at_level(logging.DEBUG):
        detect(path)
    assert [record.name for record in caplog.records if record.name.startswith("core")] == []
