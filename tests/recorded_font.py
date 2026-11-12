import os
import pathlib

import pikepdf
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE_07 = ROOT / "eval" / "samples" / "pdfs" / "07_arabic_circular_two_column.pdf"
RECORDED_ARABIC_FONT = "DejaVu"


def font_names(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    with pikepdf.open(path) as pdf:
        for page in pdf.pages:
            fonts = page.obj.get("/Resources", {}).get("/Font", {})
            names.update(str(font.get("/BaseFont", "")) for font in fonts.values())
    return names


def uses_recorded_font() -> bool:
    return any(RECORDED_ARABIC_FONT in name for name in font_names(SAMPLE_07))


def require_in_ci() -> None:
    if os.environ.get("CI") and not uses_recorded_font():
        pytest.fail(f"sample 07 was generated in a font other than {RECORDED_ARABIC_FONT}, so its recorded results cannot be checked in CI")
