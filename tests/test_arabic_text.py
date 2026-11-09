import pytest
from bidi.algorithm import get_display

from core.text.arabic_letters import arabic_share, fold_persian_forms, is_mostly_arabic
from core.text.bidi_restore import is_visual_arabic, restore_logical_order


def visual(logical: str) -> str:
    reshaper = pytest.importorskip("arabic_reshaper")
    shown = get_display(reshaper.reshape(logical), base_dir="R")
    assert isinstance(shown, str)
    return shown


@pytest.mark.parametrize("logical", ["أولا: الهدف", "خامسا: الاستفسارات", "شاكرين لكم حسن تعاونكم."])
def test_restore_returns_logical_text_for_simple_lines(logical):
    line = visual(logical)
    assert line != logical
    assert is_visual_arabic(line)
    assert restore_logical_order(line) == logical


def test_logical_arabic_and_latin_are_not_visual():
    assert not is_visual_arabic("أولا: الهدف")
    assert not is_visual_arabic("Citizen Services Department")


@pytest.mark.parametrize(("service", "arabic"), [
    ("مراکز", "مراكز"),
    ("تمدید", "تمديد"),
    ("یرجی", "يرجى"),
    ("یومیا", "يوميا"),
    ("Sample City", "Sample City"),
])
def test_persian_letter_forms_fold_to_arabic(service, arabic):
    assert fold_persian_forms(service) == arabic


def test_arabic_share_counts_letters_only():
    assert arabic_share("رقم 5500 info") == 3 / 7
    assert is_mostly_arabic("تعميم رقم ١٤")
    assert not is_mostly_arabic("Page 1 of 2")
    assert arabic_share("123") == 0.0
