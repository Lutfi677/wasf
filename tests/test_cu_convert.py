import json
import pathlib

import pytest

cu_convert = pytest.importorskip("cu_convert")

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "eval" / "fixtures" / "cu"


def response(paragraphs, tables=(), fields=None, unit="inch"):
    content = {
        "unit": unit,
        "pages": [{"pageNumber": 1, "width": 8.5, "height": 11}, {"pageNumber": 2, "width": 8.5, "height": 11}],
        "paragraphs": list(paragraphs),
        "tables": list(tables),
    }
    if fields is not None:
        content["fields"] = fields
    return {"analyzerId": "prebuilt-layout", "apiVersion": "2025-11-01", "contents": [content]}


def test_paragraphs_become_blocks_in_points():
    result = cu_convert.convert(response([
        {"content": "Title", "role": "title", "source": "D(1,1,1,4,1,4,1.5,1,1.5)"},
        {"content": "  ", "source": "D(1,1,2,2,2,2,3,1,3)"},
        {"content": "Body", "source": "D(2,1,2,3,2,3,2.5,1,2.5)"},
    ]), "prebuilt-layout")
    assert result["pages"] == [{"number": 1, "width": 612.0, "height": 792.0}, {"number": 2, "width": 612.0, "height": 792.0}]
    found = [(b["text"], b["role"], b["page"], b["reading_order"]) for b in result["blocks"]]
    assert found == [("Title", "title", 1, 0), ("Body", None, 2, 1)]
    assert result["blocks"][0]["box"] == [72.0, 72.0, 288.0, 108.0]
    assert result["version"] == "prebuilt-layout 2025-11-01"


def test_a_paragraph_over_two_pages_takes_its_first_page():
    result = cu_convert.convert(response([{"content": "Split", "source": "D(1,1,10,2,10,2,10.5,1,10.5);D(2,1,1,2,1,2,1.5,1,1.5)"}]), "x")
    assert result["blocks"][0]["page"] == 1
    assert result["blocks"][0]["box"] == [72.0, 720.0, 144.0, 756.0]


def test_table_cells_keep_their_kind():
    table = {"source": "D(2,1,1,7,1,7,3,1,3)", "cells": [
        {"rowIndex": 0, "columnIndex": 0, "content": "Item", "kind": "columnHeader"},
        {"rowIndex": 1, "columnIndex": 0, "content": "Tea"},
    ]}
    result = cu_convert.convert(response([], [table]), "x")
    assert result["tables"] == [{"id": "x-table-0", "page": 2, "cells": [
        {"row": 0, "column": 0, "text": "Item", "kind": "columnHeader"},
        {"row": 1, "column": 0, "text": "Tea", "kind": "content"},
    ]}]


def test_fields_read_string_values():
    fields = {"title": {"type": "string", "valueString": "Annual report"}, "language": {"type": "string"}}
    assert cu_convert.fields(response([], fields=fields)) == {"title": "Annual report", "language": None}


def test_unknown_unit_is_refused():
    with pytest.raises(ValueError):
        cu_convert.convert(response([], unit="cm"), "x")


def recorded():
    paths = sorted(FIXTURES.glob("*/*.json"))
    if not paths:
        pytest.skip("no Content Understanding fixtures recorded")
    return paths


def test_every_fixture_converts_with_boxes_on_the_page():
    for path in recorded():
        result = cu_convert.convert(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
        sizes = {page["number"]: (page["width"], page["height"]) for page in result["pages"]}
        assert sizes, path
        assert [block["reading_order"] for block in result["blocks"]] == list(range(len(result["blocks"])))
        for block in result["blocks"]:
            width, height = sizes[block["page"]]
            left, top, right, bottom = block["box"]
            assert -2 <= left <= right <= width + 2, path
            assert -2 <= top <= bottom <= height + 2, path
