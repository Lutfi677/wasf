from pathlib import Path

from core.extract import pdf_lines
from core.extract.pdf_lines import Line
from core.extract.shapes import Block, Result
from core.structure import headings, links, lists
from core.text.bidi_restore import is_visual_arabic, restore_logical_order

ENGINE = "wasf-rules"


def union(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def make_block(lines: list[Line], indexes: list[int], role: str | None, reading_order: int) -> Block:
    first = lines[indexes[0]]
    return {
        "id": f"{ENGINE}-{reading_order}",
        "page": first["page"],
        "role": role,
        "text": " ".join(lines[index]["text"] for index in indexes),
        "box": union([lines[index]["box"] for index in indexes]),
        "reading_order": reading_order,
        "engine": ENGINE,
        "confidence": None,
    }


def same_heading(lines: list[Line], first: int, other: int) -> bool:
    return all(lines[first][key] == lines[other][key] for key in ("page", "group", "size"))


def build(lines: list[Line], glyphs: dict[int, list[lists.Glyph]]) -> list[Block]:
    items = lists.find_items(lines, glyphs)
    starts = {item.lines[0]: item for item in items}
    consumed = {item.marker_line for item in items if item.marker_line is not None}
    levels = headings.heading_levels(lines, {index for item in items for index in item.lines} | consumed)
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        if index in consumed:
            index += 1
        elif index in starts:
            item = starts[index]
            block = make_block(lines, item.lines, "listItem", len(blocks))
            if item.prefix and block["text"].startswith(item.prefix):
                block["text"] = block["text"][len(item.prefix):].strip()
            block["marker"] = item.marker
            blocks.append(block)
            index = item.lines[-1] + 1
        elif index in levels:
            run = [index]
            while run[-1] + 1 in levels and same_heading(lines, index, run[-1] + 1):
                run.append(run[-1] + 1)
            block = make_block(lines, run, "heading", len(blocks))
            block["level"] = levels[index]
            blocks.append(block)
            index = run[-1] + 1
        else:
            blocks.append(make_block(lines, [index], None, len(blocks)))
            index += 1
    return blocks


def restore_lines(lines: list[Line]) -> list[Line]:
    restored: list[Line] = []
    for line in lines:
        copy = line.copy()
        if is_visual_arabic(line["text"]):
            copy["text"] = restore_logical_order(line["text"])
        restored.append(copy)
    return restored


def structure(path: Path) -> Result:
    pages, lines = pdf_lines.read(path)
    lines = restore_lines(lines)
    return {
        "engine": ENGINE,
        "version": pdf_lines.version(),
        "pages": pages,
        "blocks": build(lines, lists.bullet_glyphs(path)),
        "tables": [],
        "links": links.find(path, lines),
    }
