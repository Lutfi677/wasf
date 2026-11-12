from typing import Any, cast

import pytest

from core.extract.shapes import Result
from core.model import assemble as assembly
from core.scan.lines import Line

HEADER = "columnHeader"


def block(page: int, text: str, order: int, engine: str, role: str | None = None, top: float = 100.0) -> dict[str, Any]:
    return {
        "id": f"{engine}-{order}",
        "page": page,
        "role": role,
        "text": text,
        "box": [72.0, top, 300.0, top + 12.0],
        "reading_order": order,
        "engine": engine,
        "confidence": None,
    }


def result(engine: str, blocks: list[dict[str, Any]], pages: int = 2, **extra: Any) -> Result:
    found: dict[str, Any] = {
        "engine": engine,
        "version": "1",
        "pages": [{"number": number, "width": 612.0, "height": 792.0} for number in range(1, pages + 1)],
        "blocks": blocks,
        "tables": [],
    }
    found.update(extra)
    return cast(Result, found)


def line(source: str, page: int, top: float, confidence: float, text: str = "ab 12") -> Line:
    return {
        "source": source,
        "page": page,
        "box": [0.1, top, 0.9, top + 0.02],
        "words": [{"text": word, "confidence": confidence} for word in text.split()],
    }


def test_digital_pages_come_from_the_local_provider_and_scans_from_the_service():
    local = result("local", [block(1, "Local text", 0, "local")], scan_pages=[2], lines=[])
    service = result("service", [block(1, "Service text", 0, "service"), block(2, "Scanned text", 1, "service")], lines=[])
    document = assembly.assemble(service, local)
    assert [(b.page, b.text, b.engine) for b in document.blocks] == [(1, "Local text", "local"), (2, "Scanned text", "service")]
    assert [b.reading_order for b in document.blocks] == [0, 1]


def test_a_block_is_a_heading_when_the_service_says_so_by_its_text():
    local = result("local", [block(1, "Budget  Summary", 0, "local"), block(1, "Body", 1, "local", top=130.0)], scan_pages=[], lines=[])
    service = result(
        "service",
        [block(1, "budget summary", 0, "service", role="title"), block(1, "Chart words", 1, "service", role="sectionHeading")],
        lines=[],
    )
    document = assembly.assemble(service, local)
    assert [b.role for b in document.blocks] == ["heading", None]
    assert assembly.unmatched_service_headings(document, service) == 1


def test_a_local_heading_stays_a_heading_and_levels_are_kept():
    heading = block(1, "Title", 0, "local", role="heading")
    heading["level"] = 2
    document = assembly.assemble(None, result("local", [heading], scan_pages=[], lines=[]))
    assert (document.blocks[0].role, document.blocks[0].level) == ("heading", 2)


def test_blocks_get_a_language_and_the_document_the_dominant_one():
    blocks = [block(1, "Hello world", 0, "local"), block(1, "مرحبا بالعالم أهلا وسهلا", 1, "local", top=130.0)]
    local = result("local", blocks, scan_pages=[], lines=[])
    document = assembly.assemble(None, local)
    assert [b.language for b in document.blocks] == ["en", "ar"]
    assert document.language == "ar"


def test_service_tables_get_row_headers_and_figures_and_the_local_links_are_kept():
    cells = [
        {"row": 0, "column": 0, "text": "Item", "kind": HEADER},
        {"row": 0, "column": 1, "text": "Fee", "kind": HEADER},
        {"row": 1, "column": 0, "text": "Tea", "kind": "content"},
        {"row": 1, "column": 1, "text": "$4", "kind": "content"},
    ]
    service = result(
        "service",
        [],
        tables=[{"id": "service-table-0", "page": 1, "cells": cells}],
        figures=[{"id": "figure-0", "page": 1, "box": [0.0, 0.0, 50.0, 50.0], "caption": "A chart"}],
    )
    links = [{"id": "link-0", "page": 1, "box": [1.0, 1.0, 20.0, 9.0], "text": "here", "target": "https://example.org"}]
    local = result("local", [], scan_pages=[], lines=[], links=links)
    document = assembly.assemble(service, local)
    assert [c.kind for c in document.tables[0].cells] == [HEADER, HEADER, "rowHeader", "content"]
    assert [f.caption for f in document.figures] == ["A chart"]
    assert [link.target for link in document.links] == ["https://example.org"]


def test_a_scan_with_both_readers_gets_regions_in_points():
    local = result("local", [], scan_pages=[1], lines=[line("tesseract", 1, 0.5, 30.0)])
    service = result("service", [block(1, "Scanned", 0, "service")], lines=[line("service", 1, 0.5, 30.0, "ab 14")])
    document = assembly.assemble(service, local)
    assert len(document.regions) == 1
    region = document.regions[0]
    assert region.page == 1
    assert region.box == pytest.approx([61.2, 396.0, 550.8, 411.84])
    assert set(region.reasons) == {"low_confidence_tesseract", "low_confidence_service", "digits_differ"}
    assert document.engines == ["local", "service", "tesseract"]


def test_a_scan_with_one_reader_uses_the_line_rule_alone():
    local = result("local", [], scan_pages=[1], lines=[])
    service = result("service", [block(1, "Scanned", 0, "service")], lines=[line("service", 1, 0.2, 99.0), line("service", 1, 0.6, 40.0)])
    document = assembly.assemble(service, local)
    assert [r.reasons for r in document.regions] == [["low_confidence_service"]]
    assert document.regions[0].box[1] == pytest.approx(0.6 * 792)


def test_a_scan_nobody_read_goes_to_a_person_as_a_whole_page():
    document = assembly.assemble(None, result("local", [], scan_pages=[2], lines=[]))
    assert [(r.page, r.reasons, r.box) for r in document.regions] == [(2, ["scan_not_read"], [0.0, 0.0, 612.0, 792.0])]


def test_a_service_only_document_has_no_regions_and_no_links():
    document = assembly.assemble(result("service", [block(1, "Text", 0, "service")]), None)
    assert (document.regions, document.links, document.engines) == ([], [], ["service"])


def test_the_providers_must_agree_on_the_page_count():
    with pytest.raises(ValueError, match="page count"):
        assembly.assemble(result("service", [], pages=3), result("local", [], pages=2, scan_pages=[], lines=[]))


def test_a_document_needs_a_provider():
    with pytest.raises(ValueError):
        assembly.assemble(None, None)
