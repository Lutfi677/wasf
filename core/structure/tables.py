import re

from core.extract.shapes import Table

HEADER_KINDS = {"columnHeader", "stubHead"}
NUMBER = re.compile(r"[\s$+\-%.,\d]*\d[\s$+\-%.,\d]*M?")


def is_number(text: str) -> bool:
    return NUMBER.fullmatch(text.strip()) is not None


def header_rows(table: Table) -> set[int]:
    return {cell["row"] for cell in table["cells"] if cell["kind"] in HEADER_KINDS}


def stub_columns(table: Table) -> list[int]:
    headers = header_rows(table)
    if not headers:
        return []
    body = [cell for cell in table["cells"] if cell["row"] not in headers]
    stub: list[int] = []
    for column in sorted({cell["column"] for cell in body}):
        texts = [cell["text"] for cell in body if cell["column"] == column and cell["text"].strip()]
        if not texts or any(is_number(text) for text in texts):
            break
        stub.append(column)
    if any(is_number(cell["text"]) for cell in body if cell["column"] not in stub):
        return stub
    return []


def mark_row_headers(table: Table) -> Table:
    stub = set(stub_columns(table))
    if not stub:
        return table
    headers = header_rows(table)
    cells = []
    for cell in table["cells"]:
        marked = cell.copy()
        if cell["column"] in stub and cell["row"] not in headers and cell["kind"] == "content":
            marked["kind"] = "rowHeader"
        cells.append(marked)
    return {"id": table["id"], "page": table["page"], "cells": cells}
