import re
from typing import Any, TypedDict

SOURCE = re.compile(r"D\((\d+),([^)]*)\)")
PERCENT = 100.0


class Word(TypedDict):
    text: str
    confidence: float


class Line(TypedDict):
    source: str
    page: int
    box: list[float]
    words: list[Word]


def text_of(line: Line) -> str:
    return " ".join(word["text"] for word in line["words"])


def tesseract_lines(page: dict[str, Any]) -> list[Line]:
    data = page["data"]
    width, height = page["width"], page["height"]
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for index, text in enumerate(data["text"]):
        if text.strip() and float(data["conf"][index]) >= 0:
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            grouped.setdefault(key, []).append(index)
    lines: list[Line] = []
    for indexes in grouped.values():
        left = min(data["left"][i] for i in indexes)
        top = min(data["top"][i] for i in indexes)
        right = max(data["left"][i] + data["width"][i] for i in indexes)
        bottom = max(data["top"][i] + data["height"][i] for i in indexes)
        lines.append({
            "source": "tesseract",
            "page": page["number"],
            "box": [left / width, top / height, right / width, bottom / height],
            "words": [{"text": data["text"][i].strip(), "confidence": float(data["conf"][i])} for i in indexes],
        })
    return lines


def polygon_box(source: str | None, page: int, width: float, height: float) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for number, values in SOURCE.findall(source or ""):
        if int(number) == page:
            coordinates = [float(value) for value in values.split(",")]
            xs += coordinates[0::2]
            ys += coordinates[1::2]
    if not xs:
        return None
    return [min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height]


def service_lines(response: dict[str, Any]) -> list[Line]:
    lines: list[Line] = []
    for page in response["contents"][0].get("pages", []):
        number, width, height = page["pageNumber"], page["width"], page["height"]
        words = page.get("words", [])
        for entry in page.get("lines", []):
            box = polygon_box(entry.get("source"), number, width, height)
            if box is None:
                continue
            start = entry["span"]["offset"]
            end = start + entry["span"]["length"]
            members = [word for word in words if start <= word["span"]["offset"] < end]
            lines.append({
                "source": "service",
                "page": number,
                "box": box,
                "words": [{"text": word["content"], "confidence": (word.get("confidence") or 0.0) * PERCENT} for word in members],
            })
    return lines
