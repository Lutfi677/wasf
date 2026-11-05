import pytest

measure = pytest.importorskip("measure")


def test_black_on_white_is_21_to_1():
    assert round(measure.contrast_ratio((0, 0, 0), (255, 255, 255)), 2) == 21.0


def test_contrast_ratio_does_not_depend_on_order():
    assert measure.contrast_ratio((10, 80, 120), (240, 240, 200)) == measure.contrast_ratio((240, 240, 200), (10, 80, 120))


def test_equal_colours_give_1_to_1():
    assert round(measure.contrast_ratio((120, 120, 120), (120, 120, 120)), 2) == 1.0


@pytest.mark.parametrize("title", ["Microsoft Word - Minutes 03-12-26 DRAFT.doc", "form_v2.indd", "Document1", "Untitled", "report.pdf"])
def test_file_names_and_defaults_are_bad_titles(title):
    assert measure.is_bad_title(title)


@pytest.mark.parametrize("title", ["City Council Regular Meeting Minutes, March 12, 2026", "Service Request Form"])
def test_real_titles_are_not_bad_titles(title):
    assert not measure.is_bad_title(title)


@pytest.mark.parametrize("text", ["click here", "Click here.", "here", "Read more"])
def test_vague_link_text(text):
    assert measure.is_vague_link_text(text)


def test_descriptive_link_text_is_not_vague():
    assert not measure.is_vague_link_text("Download the 2026 budget summary")


def test_url_pattern_drops_trailing_punctuation():
    match = measure.URL_PATTERN.search("or visit https://www.example.org/welcome.")
    assert match.group(0) == "https://www.example.org/welcome"


def test_plan_counts_add_up_to_31():
    assert sum(measure.PLAN_COUNTS.values()) == 31
