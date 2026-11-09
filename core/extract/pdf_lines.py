import collections
import importlib.metadata
from pathlib import Path
from typing import TypedDict

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTAnno, LTChar, LTTextContainer, LTTextLine

from core.extract.shapes import Page

BOLD_NAMES = ("bold", "black", "heavy")


class Char(TypedDict):
    text: str
    box: list[float] | None


class Line(TypedDict):
    page: int
    group: int
    text: str
    box: list[float]
    size: float
    bold: bool
    chars: list[Char]


def is_bold(fontname: str) -> bool:
    name = fontname.lower()
    return any(word in name for word in BOLD_NAMES)


def read_line(line: LTTextLine, page: int, group: int, left: float, top: float) -> Line | None:
    chars: list[Char] = []
    sizes: collections.Counter[float] = collections.Counter()
    bold = True
    for item in line:
        if isinstance(item, LTChar):
            chars.append({"text": item.get_text(), "box": [item.x0 - left, top - item.y1, item.x1 - left, top - item.y0]})
            if item.get_text().strip():
                sizes[round(item.size, 1)] += 1
                bold = bold and is_bold(item.fontname)
        elif isinstance(item, LTAnno):
            chars.append({"text": item.get_text(), "box": None})
    text = line.get_text().strip()
    if not text or not sizes:
        return None
    box = [line.x0 - left, top - line.y1, line.x1 - left, top - line.y0]
    return {
        "page": page,
        "group": group,
        "text": text,
        "box": [round(value, 2) for value in box],
        "size": sizes.most_common(1)[0][0],
        "bold": bold,
        "chars": chars,
    }


def read(path: Path) -> tuple[list[Page], list[Line]]:
    pages: list[Page] = []
    lines: list[Line] = []
    for number, layout in enumerate(extract_pages(str(path), laparams=LAParams()), start=1):
        left, _, _, top = layout.bbox
        pages.append({"number": number, "width": round(layout.width, 2), "height": round(layout.height, 2)})
        for group, element in enumerate(layout):
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if isinstance(line, LTTextLine):
                    found = read_line(line, number, group, left, top)
                    if found is not None:
                        lines.append(found)
    return pages, lines


def version() -> str:
    return f"pdfminer.six {importlib.metadata.version('pdfminer.six')}"
