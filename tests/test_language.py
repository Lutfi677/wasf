import pytest

from core.text import language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello world", "en"),
        ("مرحبا بالعالم", "ar"),
        ("12 345 ... 6", None),
        ("", None),
        ("مرحبا بالعالم عالم Hi", "ar"),
        ("Opening hours الساعات", "en"),
    ],
)
def test_a_text_takes_the_script_with_more_letters(text, expected):
    assert language.of_text(text) == expected


def test_a_document_takes_the_script_with_more_letters_overall():
    assert language.dominant(["Hello", "مرحبا بالعالم أهلا وسهلا", "12"]) == "ar"
    assert language.dominant(["Hello there", "مرحبا"]) == "en"


def test_a_document_without_letters_has_no_language():
    assert language.dominant(["12", "34", ""]) is None
    assert language.dominant([]) is None
