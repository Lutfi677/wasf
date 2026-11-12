import re
from typing import Any

from core.extract.shapes import Block, Cell, Figure, Page, Result, Table
from core.scan.lines import service_lines
from core.text.arabic_letters import fold_persian_forms, is_mostly_arabic

POINTS_PER_UNIT = {"inch": 72.0, "pixel": 1.0}
SOURCE = re.compile(r"D\((\d+),([^)]*)\)")
LAYOUT = "prebuilt-layout"


def regions(source: str | None) -> list[tuple[int, list[float]]]:
    return [(int(match.group(1)), [float(n) for n in match.group(2).split(",")]) for match in SOURCE.finditer(source or "")]


def first_page_box(source: str | None, scale: float) -> tuple[int, list[float] | None]:
    found = regions(source)
    if not found:
        return 0, None
    page = found[0][0]
    xs = [value for number, values in found if number == page for value in values[0::2]]
    ys = [value for number, values in found if number == page for value in values[1::2]]
    return page, [round(min(xs) * scale, 2), round(min(ys) * scale, 2), round(max(xs) * scale, 2), round(max(ys) * scale, 2)]


def content_of(response: dict[str, Any]) -> dict[str, Any]:
    return response["contents"][0]


def convert_cell(cell: dict[str, Any], scale: float) -> Cell:
    converted: Cell = {
        "row": cell["rowIndex"],
        "column": cell["columnIndex"],
        "text": cell.get("content") or "",
        "kind": cell.get("kind") or "content",
    }
    _, box = first_page_box(cell.get("source"), scale)
    if box is not None:
        converted["box"] = box
    return converted


def convert_figures(content: dict[str, Any], scale: float) -> list[Figure]:
    figures: list[Figure] = []
    for figure in content.get("figures", []):
        page, box = first_page_box(figure.get("source"), scale)
        if box is None:
            continue
        caption = (figure.get("caption") or {}).get("content")
        figures.append({"id": f"figure-{len(figures)}", "page": page, "box": box, "caption": caption})
    return figures


def convert(response: dict[str, Any], engine: str) -> Result:
    content = content_of(response)
    unit = content.get("unit", "inch")
    if unit not in POINTS_PER_UNIT:
        raise ValueError(f"unknown unit {unit}")
    scale = POINTS_PER_UNIT[unit]
    pages: list[Page] = [
        {"number": page["pageNumber"], "width": round(page["width"] * scale, 2), "height": round(page["height"] * scale, 2)}
        for page in content.get("pages", [])
    ]
    blocks: list[Block] = []
    for paragraph in content.get("paragraphs", []):
        text = (paragraph.get("content") or "").strip()
        if not text:
            continue
        page, box = first_page_box(paragraph.get("source"), scale)
        blocks.append({
            "id": f"{engine}-{len(blocks)}",
            "page": page,
            "role": paragraph.get("role"),
            "text": text,
            "box": box,
            "reading_order": len(blocks),
            "engine": engine,
            "confidence": None,
        })
    tables: list[Table] = []
    for index, table in enumerate(content.get("tables", [])):
        page, _ = first_page_box(table.get("source"), scale)
        cells = [convert_cell(cell, scale) for cell in table.get("cells", [])]
        tables.append({"id": f"{engine}-table-{index}", "page": page, "cells": cells})
    version = f"{response.get('analyzerId', engine)} {response.get('apiVersion', '')}".strip()
    return {
        "engine": engine,
        "version": version,
        "pages": pages,
        "blocks": blocks,
        "tables": tables,
        "figures": convert_figures(content, scale),
    }


def fold_arabic(result: Result) -> Result:
    if not is_mostly_arabic(" ".join(block["text"] for block in result["blocks"])):
        return result
    for block in result["blocks"]:
        block["text"] = fold_persian_forms(block["text"])
    for table in result["tables"]:
        for cell in table["cells"]:
            cell["text"] = fold_persian_forms(cell["text"])
    return result


def fields(response: dict[str, Any]) -> dict[str, str | None]:
    found = content_of(response).get("fields") or {}
    return {name: value.get("valueString") for name, value in found.items()}


def read(response: dict[str, Any]) -> Result:
    result = fold_arabic(convert(response, LAYOUT))
    result["lines"] = service_lines(response)
    return result
