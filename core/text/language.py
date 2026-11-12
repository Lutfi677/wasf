from core.text.arabic_letters import ARABIC, LETTERS

ARABIC_TAG = "ar"
LATIN_TAG = "en"


def counts(text: str) -> tuple[int, int]:
    arabic = len(ARABIC.findall(text))
    return arabic, len(LETTERS.findall(text)) - arabic


def of_text(text: str) -> str | None:
    arabic, latin = counts(text)
    if arabic + latin == 0:
        return None
    return ARABIC_TAG if arabic >= latin else LATIN_TAG


def dominant(texts: list[str]) -> str | None:
    arabic = latin = 0
    for text in texts:
        found = counts(text)
        arabic += found[0]
        latin += found[1]
    if arabic + latin == 0:
        return None
    return ARABIC_TAG if arabic >= latin else LATIN_TAG
