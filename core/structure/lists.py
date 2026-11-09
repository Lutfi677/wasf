import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

from core.extract.pdf_lines import Line
from core.text.arabic_letters import is_mostly_arabic

BULLET_GLYPHS = "•◦▪▫‣●○■□·"
MARKER_FORMS = (
    ("number", r"\d{1,3}[.)]"),
    ("letter", r"[A-Za-z][.)]"),
    ("bullet", f"[{BULLET_GLYPHS}]"),
)
PREFIXES = tuple((kind, re.compile(form + r"(?=\s)")) for kind, form in MARKER_FORMS)
WHOLE = tuple((kind, re.compile(form)) for kind, form in MARKER_FORMS)
UNMAPPED = re.compile(r"\(cid:\d+\)")
GLYPH_GAP = 24.0
START_TOLERANCE = 3.0
INDENT_TOLERANCE = 2.0
NEXT_LINE = 2.0

Glyph = tuple[str, list[float]]


@dataclass
class Item:
    lines: list[int]
    marker: str
    kind: str
    prefix: str
    text_left: float
    page: int
    marker_line: int | None
    right_to_left: bool = False


def bullet_glyphs(path: Path) -> dict[int, list[Glyph]]:
    found: dict[int, list[Glyph]] = {}
    document = pypdfium2.PdfDocument(str(path))
    try:
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            _, height = page.get_size()
            glyphs: list[Glyph] = []
            for position, character in enumerate(textpage.get_text_range()):
                if character in BULLET_GLYPHS:
                    left, bottom, right, top = textpage.get_charbox(position)
                    glyphs.append((character, [left, height - top, right, height - bottom]))
            found[index + 1] = glyphs
            textpage.close()
            page.close()
    finally:
        document.close()
    return found


def same_row(line: Line, box: list[float]) -> bool:
    overlap = min(line["box"][3], box[3]) - max(line["box"][1], box[1])
    return overlap > 0.5 * (box[3] - box[1])


def beside(line: Line, box: list[float]) -> bool:
    return same_row(line, box) and box[0] < line["box"][0] and 0 <= line["box"][0] - box[2] <= GLYPH_GAP


def after(line: Line, box: list[float]) -> bool:
    return same_row(line, box) and box[2] > line["box"][2] and 0 <= box[0] - line["box"][2] <= GLYPH_GAP


def at_start(line: Line, box: list[float]) -> bool:
    return same_row(line, box) and abs(box[0] - line["box"][0]) <= START_TOLERANCE


def left_after(line: Line, skipped: int) -> float:
    seen = 0
    for char in line["chars"]:
        if char["box"] is None or not char["text"].strip():
            continue
        if seen == skipped:
            return char["box"][0]
        seen += 1
    return line["box"][0]


def whole_marker(text: str) -> tuple[str, str] | None:
    for kind, pattern in WHOLE:
        if pattern.fullmatch(text):
            return text, kind
    return None


Found = tuple[str, str, str, float, int | None]


def marker_of(line: Line, glyphs: list[Glyph], alone: dict[int, tuple[str, str]], lines: list[Line]) -> Found | None:
    for kind, pattern in PREFIXES:
        match = pattern.match(line["text"])
        if match:
            marker = match.group(0)
            return marker, kind, marker, left_after(line, len(marker)), None
    unmapped = UNMAPPED.match(line["text"])
    if unmapped:
        character = next((character for character, box in glyphs if at_start(line, box)), None)
        if character is not None:
            return character, "bullet", unmapped.group(0), left_after(line, 1), None
    for index, (marker, kind) in alone.items():
        if lines[index]["page"] == line["page"] and beside(line, lines[index]["box"]):
            return marker, kind, "", line["box"][0], index
    character = next((character for character, box in glyphs if beside(line, box)), None)
    if character is not None:
        return character, "bullet", "", line["box"][0], None
    if is_mostly_arabic(line["text"]):
        character = next((character for character, box in glyphs if after(line, box)), None)
        if character is not None:
            return character, "bullet", "", line["box"][2], None
    return None


def continues(previous: Line, line: Line, text_edge: float, right_to_left: bool = False) -> bool:
    height = previous["box"][3] - previous["box"][1]
    step = line["box"][1] - previous["box"][1]
    edge = line["box"][2] if right_to_left else line["box"][0]
    return line["page"] == previous["page"] and abs(edge - text_edge) <= INDENT_TOLERANCE and 0 < step <= NEXT_LINE * height


def find_items(lines: list[Line], glyphs: dict[int, list[Glyph]]) -> list[Item]:
    alone = {index: found for index, line in enumerate(lines) if (found := whole_marker(line["text"])) is not None}
    items: list[Item] = []
    current: Item | None = None
    for index, line in enumerate(lines):
        if index in alone:
            current = None
            continue
        found = marker_of(line, glyphs.get(line["page"], []), alone, lines)
        if found is not None:
            marker, kind, prefix, text_left, marker_line = found
            right_to_left = is_mostly_arabic(line["text"])
            edge = line["box"][2] if right_to_left else text_left
            current = Item([index], marker, kind, prefix, edge, line["page"], marker_line, right_to_left)
            items.append(current)
        elif current is not None and continues(lines[current.lines[-1]], line, current.text_left, current.right_to_left):
            current.lines.append(index)
        else:
            current = None
    return items
