from pathlib import Path

import pikepdf

from core.extract.pdf_lines import Line
from core.extract.shapes import Link


def link_annotations(path: Path) -> list[tuple[int, list[float], str | None]]:
    found: list[tuple[int, list[float], str | None]] = []
    with pikepdf.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            left, _, _, top = (float(value) for value in page.mediabox)
            for annotation in page.obj.get("/Annots", []):
                if annotation.get("/Subtype") != "/Link" or "/Rect" not in annotation:
                    continue
                x0, y0, x1, y1 = (float(value) for value in annotation["/Rect"])
                box = [min(x0, x1) - left, top - max(y0, y1), max(x0, x1) - left, top - min(y0, y1)]
                action = annotation.get("/A")
                target = str(action["/URI"]) if action is not None and "/URI" in action else None
                found.append((number, [round(value, 2) for value in box], target))
    return found


def inside(char_box: list[float], box: list[float]) -> bool:
    centre_x = (char_box[0] + char_box[2]) / 2
    centre_y = (char_box[1] + char_box[3]) / 2
    return box[0] <= centre_x <= box[2] and box[1] <= centre_y <= box[3]


def visible_text(lines: list[Line], page: int, box: list[float]) -> str:
    parts: list[str] = []
    for line in lines:
        if line["page"] != page:
            continue
        flags = [char["box"] is not None and inside(char["box"], box) for char in line["chars"]]
        if not any(flags):
            continue
        first = flags.index(True)
        last = len(flags) - 1 - flags[::-1].index(True)
        chosen = line["chars"][first : last + 1]
        kept = flags[first : last + 1]
        parts.append("".join(char["text"] for char, keep in zip(chosen, kept, strict=True) if keep or not char["text"].strip()))
    return " ".join(" ".join(parts).split())


def find(path: Path, lines: list[Line]) -> list[Link]:
    return [
        {"id": f"link-{index}", "page": page, "box": box, "text": visible_text(lines, page, box), "target": target}
        for index, (page, box, target) in enumerate(link_annotations(path))
    ]
