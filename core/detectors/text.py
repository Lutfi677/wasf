import unicodedata

QUOTE_LIMIT = 80


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def quoted(text: str) -> str:
    cleaned = normalise(text)
    if len(cleaned) > QUOTE_LIMIT:
        cleaned = cleaned[: QUOTE_LIMIT - 3] + "..."
    return f"'{cleaned}'"
