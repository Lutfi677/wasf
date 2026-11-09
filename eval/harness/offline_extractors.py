import importlib.metadata
import os
import pathlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable

import pypdfium2
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextContainer
from result_types import Block, Page, Result

XHTML = "{http://www.w3.org/1999/xhtml}"
LINE_BREAKS = {"\r", "\n"}


class ToolMissing(RuntimeError):
    pass


def make_block(engine: str, page: int, text: str, box: list[float] | None, reading_order: int) -> Block:
    return {
        "id": f"{engine}-{reading_order}",
        "page": page,
        "role": None,
        "text": text,
        "box": None if box is None else [round(value, 2) for value in box],
        "reading_order": reading_order,
        "engine": engine,
        "confidence": None,
    }


def pdfminer_result(path: pathlib.Path) -> Result:
    engine = "pdfminer.six"
    pages: list[Page] = []
    blocks: list[Block] = []
    for number, layout in enumerate(extract_pages(str(path), laparams=LAParams()), start=1):
        left, _, _, top = layout.bbox
        pages.append({"number": number, "width": round(layout.width, 2), "height": round(layout.height, 2)})
        for element in layout:
            if not isinstance(element, LTTextContainer):
                continue
            text = element.get_text().strip()
            if not text:
                continue
            x0, y0, x1, y1 = element.bbox
            blocks.append(make_block(engine, number, text, [x0 - left, top - y1, x1 - left, top - y0], len(blocks)))
    return {"engine": engine, "version": importlib.metadata.version("pdfminer.six"), "pages": pages, "blocks": blocks, "tables": []}


def line_box(boxes: list[tuple[float, float, float, float]], height: float) -> list[float] | None:
    if not boxes:
        return None
    return [min(b[0] for b in boxes), height - max(b[3] for b in boxes), max(b[2] for b in boxes), height - min(b[1] for b in boxes)]


def pdfium_lines(textpage: pypdfium2.PdfTextPage) -> list[tuple[str, list[tuple[float, float, float, float]]]]:
    lines: list[tuple[str, list[tuple[float, float, float, float]]]] = []
    characters: list[str] = []
    boxes: list[tuple[float, float, float, float]] = []
    for position, character in enumerate(textpage.get_text_range()):
        if character in LINE_BREAKS:
            lines.append(("".join(characters), boxes))
            characters, boxes = [], []
            continue
        characters.append(character)
        left, bottom, right, top = textpage.get_charbox(position)
        if right > left and top > bottom:
            boxes.append((left, bottom, right, top))
    lines.append(("".join(characters), boxes))
    return lines


def pypdfium2_result(path: pathlib.Path) -> Result:
    engine = "pypdfium2"
    pages: list[Page] = []
    blocks: list[Block] = []
    document = pypdfium2.PdfDocument(str(path))
    try:
        for index in range(len(document)):
            number = index + 1
            page = document[index]
            textpage = page.get_textpage()
            width, height = page.get_size()
            pages.append({"number": number, "width": round(width, 2), "height": round(height, 2)})
            for line, boxes in pdfium_lines(textpage):
                if line.strip():
                    blocks.append(make_block(engine, number, line.strip(), line_box(boxes, height), len(blocks)))
            textpage.close()
            page.close()
    finally:
        document.close()
    return {"engine": engine, "version": importlib.metadata.version("pypdfium2"), "pages": pages, "blocks": blocks, "tables": []}


def find_pdftotext() -> tuple[str, str]:
    candidate = os.environ.get("WASF_PDFTOTEXT") or shutil.which("pdftotext")
    if not candidate:
        raise ToolMissing("pdftotext is not installed; install poppler or set WASF_PDFTOTEXT")
    probe = subprocess.run([candidate, "-v"], capture_output=True, text=True, check=False)
    output = probe.stdout + probe.stderr
    match = re.search(r"pdftotext version (\S+)", output)
    if "Poppler" not in output or not match:
        raise ToolMissing("the pdftotext found is not poppler; set WASF_PDFTOTEXT to poppler's pdftotext")
    return candidate, match.group(1)


def number(element: ET.Element, name: str) -> float:
    return float(element.get(name, "0"))


def pdftotext_result(path: pathlib.Path) -> Result:
    engine = "pdftotext"
    executable, version = find_pdftotext()
    run = subprocess.run([executable, "-bbox-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True)
    root = ET.fromstring(run.stdout)
    pages: list[Page] = []
    blocks: list[Block] = []
    for index, page in enumerate(root.iter(f"{XHTML}page")):
        page_number = index + 1
        pages.append({"number": page_number, "width": number(page, "width"), "height": number(page, "height")})
        for block in page.iter(f"{XHTML}block"):
            lines = [" ".join(word.text or "" for word in line.iter(f"{XHTML}word")) for line in block.iter(f"{XHTML}line")]
            text = "\n".join(line for line in lines if line.strip())
            if not text:
                continue
            box = [number(block, "xMin"), number(block, "yMin"), number(block, "xMax"), number(block, "yMax")]
            blocks.append(make_block(engine, page_number, text, box, len(blocks)))
    return {"engine": engine, "version": f"poppler {version}", "pages": pages, "blocks": blocks, "tables": []}


EXTRACTORS: dict[str, Callable[[pathlib.Path], Result]] = {
    "pdfminer.six": pdfminer_result,
    "pypdfium2": pypdfium2_result,
    "pdftotext": pdftotext_result,
}
