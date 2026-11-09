import re
import unicodedata

from bidi.algorithm import get_display

PRESENTATION_FORMS = re.compile("[ﭐ-﷿ﹰ-ﻼ]")


def is_visual_arabic(text: str) -> bool:
    return PRESENTATION_FORMS.search(text) is not None


def restore_logical_order(visual_line: str) -> str:
    logical = get_display(visual_line, base_dir="R")
    if not isinstance(logical, str):
        raise TypeError("python-bidi returned bytes for a text line")
    return unicodedata.normalize("NFKC", logical)
