import re
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium

from core.detectors.text import normalise, quoted
from core.findings import Finding

VAGUE_LINK_TEXTS = {"click here", "here", "read more", "more", "this link", "link", "click", "learn more"}
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)]", re.IGNORECASE)


def is_vague_link_text(text: str) -> bool:
    cleaned = re.sub(r"[^\w ]", "", normalise(text)).strip().lower()
    return cleaned in VAGUE_LINK_TEXTS


def link_rectangles(path: Path) -> list[list[tuple[float, float, float, float]]]:
    pages = []
    with pikepdf.open(path) as pdf:
        for page in pdf.pages:
            rectangles = []
            for annotation in page.obj.get("/Annots", []):
                if annotation.get("/Subtype") == "/Link" and "/Rect" in annotation:
                    left, bottom, right, top = (float(value) for value in annotation["/Rect"])
                    rectangles.append((min(left, right), min(bottom, top), max(left, right), max(bottom, top)))
            pages.append(rectangles)
    return pages


def is_covered(textpage, start: int, end: int, rectangles) -> bool | None:
    boxes = [textpage.get_charbox(position) for position in range(start, end)]
    boxes = [box for box in boxes if box[2] > box[0] and box[3] > box[1]]
    if not boxes:
        return None
    centre_x = (min(box[0] for box in boxes) + max(box[2] for box in boxes)) / 2
    centre_y = (min(box[1] for box in boxes) + max(box[3] for box in boxes)) / 2
    return any(left <= centre_x <= right and bottom <= centre_y <= top for left, bottom, right, top in rectangles)


def detect_links(path: Path) -> list[Finding]:
    found = []
    rectangles = link_rectangles(path)
    doc = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(doc)):
            page = doc[index]
            textpage = page.get_textpage()
            for left, bottom, right, top in rectangles[index]:
                text = textpage.get_text_bounded(left, bottom, right, top)
                if is_vague_link_text(text):
                    evidence = f"The link text {quoted(text)} does not say where the link goes"
                    found.append(Finding(defect="VAGUE_LINK", page=index + 1, evidence=evidence))
            for match in URL_PATTERN.finditer(textpage.get_text_range()):
                if is_covered(textpage, match.start(), match.end(), rectangles[index]) is False:
                    evidence = f"The web address {quoted(match.group(0))} is typed as text and is not a link"
                    found.append(Finding(defect="RAW_URL", page=index + 1, evidence=evidence))
            textpage.close()
            page.close()
    finally:
        doc.close()
    return found
