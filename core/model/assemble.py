from typing import Any

from core.extract.shapes import Result
from core.model.document import Document
from core.scan import crosscheck, line_rule
from core.scan.lines import Line
from core.structure import tables as table_rules
from core.text import language

HEADING_ROLES = {"title", "heading", "sectionHeading"}
SCAN_ENGINE = "tesseract"
WHOLE_PAGE = [0.0, 0.0, 1.0, 1.0]


def normal(text: str) -> str:
    return " ".join(text.casefold().split())


def service_headings(service: Result | None) -> set[str]:
    if service is None:
        return set()
    return {normal(block["text"]) for block in service["blocks"] if block["role"] in HEADING_ROLES}


def page_numbers(service: Result | None, local: Result | None) -> list[dict[str, Any]]:
    if local is not None and service is not None and len(local["pages"]) != len(service["pages"]):
        raise ValueError("the providers disagree on the page count")
    return [dict(page) for page in (local or service or {"pages": []})["pages"]]


def chosen_blocks(service: Result | None, local: Result | None, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scans = set(local.get("scan_pages", [])) if local is not None else set()
    upgrade = service_headings(service) if local is not None else set()
    chosen: list[dict[str, Any]] = []
    for page in pages:
        number = page["number"]
        if local is not None and number not in scans:
            source, headings = local, upgrade
        elif service is not None:
            source, headings = service, set()
        else:
            continue
        for block in source["blocks"]:
            if block["page"] != number:
                continue
            copy: dict[str, Any] = dict(block)
            if copy["role"] is None and normal(copy["text"]) in headings:
                copy["role"] = "heading"
            chosen.append(copy)
    for position, block in enumerate(chosen):
        block["reading_order"] = position
        block["language"] = language.of_text(block["text"])
    return chosen


def page_regions(number: int, tesseract: list[Line], service: list[Line]) -> list[dict[str, Any]]:
    if tesseract and service:
        return [dict(region) for region in crosscheck.route(tesseract, service)]
    lines = tesseract or service
    if lines:
        return [
            {"page": number, "box": line["box"], "reasons": [f"low_confidence_{line['source']}"]}
            for line in lines
            if line_rule.goes_to_person(line)
        ]
    return [{"page": number, "box": WHOLE_PAGE, "reasons": ["scan_not_read"]}]


def regions_for_person(service: Result | None, local: Result | None, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if local is None:
        return []
    sizes = {page["number"]: page for page in pages}
    found: list[dict[str, Any]] = []
    for number in sorted(local.get("scan_pages", [])):
        tesseract = [line for line in local.get("lines", []) if line["page"] == number]
        read = [line for line in (service.get("lines", []) if service is not None else []) if line["page"] == number]
        for region in page_regions(number, tesseract, read):
            left, top, right, bottom = region["box"]
            width, height = sizes[number]["width"], sizes[number]["height"]
            region["box"] = [left * width, top * height, right * width, bottom * height]
            found.append(region)
    return found


def engines_of(service: Result | None, local: Result | None, regions: list[dict[str, Any]]) -> list[str]:
    names = [result["engine"] for result in (local, service) if result is not None]
    if regions and local is not None and local.get("lines"):
        names.append(SCAN_ENGINE)
    return list(dict.fromkeys(names))


def assemble(service: Result | None, local: Result | None) -> Document:
    if service is None and local is None:
        raise ValueError("a document needs at least one provider")
    pages = page_numbers(service, local)
    blocks = chosen_blocks(service, local, pages)
    tables = [table_rules.mark_row_headers(table) for table in service["tables"]] if service is not None else []
    regions = regions_for_person(service, local, pages)
    return Document.model_validate({
        "language": language.dominant([block["text"] for block in blocks]),
        "engines": engines_of(service, local, regions),
        "pages": pages,
        "blocks": blocks,
        "tables": tables,
        "links": local.get("links", []) if local is not None else [],
        "figures": service.get("figures", []) if service is not None else [],
        "regions": regions,
    })


def unmatched_service_headings(document: Document, service: Result | None) -> int:
    kept = {normal(block.text) for block in document.blocks if block.role in HEADING_ROLES}
    return len(service_headings(service) - kept)
