import re

ARABIC_LETTER = "[ؠ-يٮ-ۓکی]"
KEHEH, FARSI_YEH = "ک", "ی"
KAF, YEH, ALEF_MAKSURA = "ك", "ي", "ى"
FINAL_FARSI_YEH = re.compile(f"{FARSI_YEH}(?!{ARABIC_LETTER})")
LETTERS = re.compile("[A-Za-zؠ-يٮ-ۓکی]")
ARABIC = re.compile(ARABIC_LETTER)


def fold_persian_forms(text: str) -> str:
    text = text.replace(KEHEH, KAF)
    text = FINAL_FARSI_YEH.sub(ALEF_MAKSURA, text)
    return text.replace(FARSI_YEH, YEH)


def arabic_share(text: str) -> float:
    letters = LETTERS.findall(text)
    return len(ARABIC.findall(text)) / len(letters) if letters else 0.0


def is_mostly_arabic(text: str) -> bool:
    return arabic_share(text) >= 0.5
