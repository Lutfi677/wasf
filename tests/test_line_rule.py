import pytest

from core.scan import line_rule
from core.scan.lines import Line


def line_of(*confidences: float) -> Line:
    return {
        "source": "tesseract",
        "page": 1,
        "box": [0.1, 0.1, 0.9, 0.12],
        "words": [{"text": f"w{index}", "confidence": value} for index, value in enumerate(confidences)],
    }


def test_thresholds_are_the_plans():
    assert line_rule.AVERAGE_MINIMUM == 85.0
    assert line_rule.WORD_MINIMUM == 50.0


@pytest.mark.parametrize(
    ("confidences", "expected"),
    [
        ((95, 95, 95), False),
        ((85, 85), False),
        ((84.9, 85), True),
        ((90, 90, 70), True),
        ((100, 100, 100, 50), False),
        ((100, 100, 100, 49), True),
        ((100, 100, 100, 100, 100, 100, 100, 100, 100, 49), True),
        ((10,), True),
    ],
)
def test_a_line_goes_to_a_person_below_the_average_or_the_word_minimum(confidences, expected):
    assert line_rule.goes_to_person(line_of(*confidences)) is expected


def test_a_line_with_no_words_goes_to_a_person():
    assert line_rule.goes_to_person(line_of())


def test_average_and_lowest():
    line = line_of(100, 80, 60)
    assert line_rule.average(line) == 80
    assert line_rule.lowest(line) == 60
