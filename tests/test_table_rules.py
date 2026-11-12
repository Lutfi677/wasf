from typing import cast

import pytest

from core.extract.shapes import Table
from core.structure import tables

HEADER = "columnHeader"
CONTENT = "content"


def make(rows: list[list[tuple[str, str]]]) -> Table:
    cells = [
        {"row": row, "column": column, "text": text, "kind": kind}
        for row, values in enumerate(rows)
        for column, (text, kind) in enumerate(values)
    ]
    return cast(Table, {"id": "t", "page": 1, "cells": cells})


def kinds(table: Table) -> list[list[str]]:
    grid: dict[int, list[str]] = {}
    for cell in table["cells"]:
        grid.setdefault(cell["row"], []).append(cell["kind"])
    return [grid[row] for row in sorted(grid)]


FEES = [
    [("Category", HEADER), ("Program", HEADER), ("Fee", HEADER)],
    [("Sciences", CONTENT), ("Biology", CONTENT), ("$45", CONTENT)],
    [("Arts", CONTENT), ("Painting", CONTENT), ("$60", CONTENT)],
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$118", True),
        ("+5.7%", True),
        ("31.4", True),
        ("$31.4M", True),
        ("١٢٣", True),
        ("R-1", False),
        ("4 du/acre", False),
        ("", False),
        ("n/a", False),
    ],
)
def test_numbers_are_recognised(text, expected):
    assert tables.is_number(text) is expected


def test_leading_text_columns_become_row_headers():
    table = make(FEES)
    assert tables.stub_columns(table) == [0, 1]
    assert kinds(tables.mark_row_headers(table)) == [
        [HEADER, HEADER, HEADER],
        ["rowHeader", "rowHeader", CONTENT],
        ["rowHeader", "rowHeader", CONTENT],
    ]


def test_marking_does_not_change_the_table_it_was_given():
    table = make(FEES)
    tables.mark_row_headers(table)
    assert kinds(table)[1] == [CONTENT, CONTENT, CONTENT]


def test_only_content_cells_are_marked():
    rows = [row[:] for row in FEES]
    rows[1][0] = ("Sciences", "description")
    assert kinds(tables.mark_row_headers(make(rows)))[1] == ["description", "rowHeader", CONTENT]


def test_a_table_without_a_numeric_column_gets_no_row_headers():
    rows = [[("Day", HEADER), ("Hours", HEADER)], [("Monday", CONTENT), ("open", CONTENT)], [("Friday", CONTENT), ("closed", CONTENT)]]
    table = make(rows)
    assert tables.stub_columns(table) == []
    assert tables.mark_row_headers(table) is table


def test_a_table_without_header_rows_gets_no_row_headers():
    rows = [[("Sciences", CONTENT), ("$45", CONTENT)], [("Arts", CONTENT), ("$60", CONTENT)]]
    assert tables.stub_columns(make(rows)) == []


def test_a_numeric_first_column_gets_no_row_headers():
    rows = [[("No", HEADER), ("Name", HEADER)], [("1", CONTENT), ("Ada", CONTENT)], [("2", CONTENT), ("Grace", CONTENT)]]
    assert tables.stub_columns(make(rows)) == []


def test_a_text_column_after_a_numeric_one_is_not_a_row_header():
    rows = [
        [("Item", HEADER), ("Count", HEADER), ("Note", HEADER)],
        [("Tea", CONTENT), ("4", CONTENT), ("hot", CONTENT)],
        [("Milk", CONTENT), ("2", CONTENT), ("cold", CONTENT)],
    ]
    assert tables.stub_columns(make(rows)) == [0]


def test_blank_cells_do_not_decide_a_column():
    rows = [
        [("Category", HEADER), ("Program", HEADER), ("Fee", HEADER)],
        [("Sciences", CONTENT), ("Biology", CONTENT), ("$45", CONTENT)],
        [("", CONTENT), ("Chemistry", CONTENT), ("$45", CONTENT)],
    ]
    assert tables.stub_columns(make(rows)) == [0, 1]
