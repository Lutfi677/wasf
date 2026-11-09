import difflib
import itertools
import math
import re
import unicodedata
from fractions import Fraction
from typing import Any, NamedTuple, TypedDict

from result_types import Block, Cell, Result

SPACE = re.compile(r"\s+")
HYPHEN_BREAK = re.compile(r"-\s+")
STRUCTURE_NOTE = re.compile(r"\s*\((?:rowspan|colspan) \d+\)")
NUMBER_DECORATION = re.compile(r"[$,%+\s]")
LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,3}(?![A-Za-z])")
HEADING_ROLES = {"title", "heading", "sectionHeading"}
HEADER_KINDS = {"columnHeader", "rowHeader", "stubHead"}
EMPTY_CELL = {"", "—", "–", "-"}
TARGET_METRICS = ("text", "headings", "table_cells", "header_cells", "reading_order")
FIXED_TARGETS = {
    ("01", "header_cells"): 100,
    ("02", "header_cells"): 100,
    ("05", "parcel_lines_to_person"): 100,
}
RULE = "best baseline percent plus half the gap to 100, rounded down to a whole percent"


class Count(TypedDict):
    found: int
    of: int


class ExpectedCell(NamedTuple):
    row: int
    column: int
    value: Any
    header: bool


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = SPACE.sub(" ", text).strip()
    return HYPHEN_BREAK.sub("-", text)


def comparable(text: str) -> str:
    return normalise(text).casefold()


def ordered(result: Result) -> list[Block]:
    return sorted(result["blocks"], key=lambda block: block["reading_order"])


def document_text(result: Result) -> str:
    return " ".join(block["text"] for block in ordered(result))


def page_text(result: Result, page: int) -> str:
    return " ".join(block["text"] for block in ordered(result) if block["page"] == page)


def coverage(reference: str, extracted: str) -> Count:
    expected, actual = normalise(reference), normalise(extracted)
    matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    return {"found": sum(block.size for block in matcher.get_matching_blocks()), "of": len(expected)}


def logical_body(source: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in source["right_column_read_first"] + source["left_column_read_second"]:
        parts.append(section["heading"])
        parts.extend(section["paragraphs"])
    return " ".join(parts)


def expected_cells(table: dict[str, Any]) -> list[ExpectedCell]:
    header_rows = table.get("header_rows") or [table["header_row"]]
    cells: list[ExpectedCell] = []
    for row_index, row in enumerate(header_rows):
        for column, text in enumerate(row):
            text = STRUCTURE_NOTE.sub("", text)
            if text:
                cells.append(ExpectedCell(row_index, column, text, True))
    header_columns = len(table.get("row_header_columns") or [])
    previous: list[Any] | None = None
    for offset, row in enumerate(table["rows"]):
        values = list(row.values()) if isinstance(row, dict) else list(row)
        row_index = len(header_rows) + offset
        for column, value in enumerate(values):
            if column < header_columns - 1 and previous is not None and previous[column] == value:
                continue
            cells.append(ExpectedCell(row_index, column, value, column < header_columns))
        previous = values
    return cells


def expected_tables(entry: dict[str, Any]) -> list[tuple[list[int], list[ExpectedCell]]]:
    tables: list[tuple[list[int], list[ExpectedCell]]] = []
    for table in entry.get("tables_expected", []):
        tables.append((table.get("pages") or [table["page"]], expected_cells(table)))
    for table in entry.get("expected_outputs", {}).get("tables", []):
        tables.append(([table["page"]], expected_cells({"header_row": table["columns"], "rows": table["rows"]})))
    return tables


def key_strings(entry: dict[str, Any], excluded: list[str] | None = None) -> list[str]:
    left_out = {comparable(text) for text in excluded or []}
    strings = [heading["text"] for heading in entry.get("headings_expected", [])]
    for _, cells in expected_tables(entry):
        strings.extend(cell.value for cell in cells if isinstance(cell.value, str) and any(c.isalpha() for c in cell.value))
    for field in entry.get("fields_expected", []):
        strings.extend([field["en"], field["ar"]])
    strings.extend(item["text"] for item in entry.get("pii_expected", []))
    normalised = (comparable(STRUCTURE_NOTE.sub("", text)) for text in strings)
    return list(dict.fromkeys(text for text in normalised if text and text not in left_out))


def text_score(entry: dict[str, Any], result: Result, excluded: list[str] | None = None) -> Count:
    if "ground_truth_text_per_page" in entry:
        total: Count = {"found": 0, "of": 0}
        for page, reference in enumerate(entry["ground_truth_text_per_page"], start=1):
            part = coverage(reference, page_text(result, page))
            total = {"found": total["found"] + part["found"], "of": total["of"] + part["of"]}
        return total
    if "source_text_logical_order" in entry:
        return coverage(logical_body(entry["source_text_logical_order"]), document_text(result))
    strings = key_strings(entry, excluded)
    text = comparable(document_text(result))
    return {"found": sum(1 for string in strings if string in text), "of": len(strings)}


def heading_runs(result: Result) -> list[list[Block]]:
    runs: list[list[Block]] = []
    current: list[Block] = []
    for block in ordered(result):
        if block["role"] in HEADING_ROLES:
            if current and current[-1]["page"] != block["page"]:
                runs.append(current)
                current = []
            current.append(block)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def heading_texts(result: Result) -> tuple[set[str], list[Block]]:
    found_texts: set[str] = set()
    labelled: list[Block] = []
    for run in heading_runs(result):
        labelled.extend(run)
        for start in range(len(run)):
            for end in range(start + 1, len(run) + 1):
                found_texts.add(comparable(" ".join(block["text"] for block in run[start:end])))
    return found_texts, labelled


def headings_found(expected: list[dict[str, Any]], result: Result) -> list[bool]:
    found_texts, _ = heading_texts(result)
    return [comparable(heading["text"]) in found_texts for heading in expected]


def heading_scores(expected: list[dict[str, Any]], result: Result) -> tuple[Count, Count]:
    _, labelled = heading_texts(result)
    wanted = [comparable(heading["text"]) for heading in expected]
    recall: Count = {"found": sum(headings_found(expected, result)), "of": len(wanted)}
    precision: Count = {
        "found": sum(1 for block in labelled if any(comparable(block["text"]) in text for text in wanted)),
        "of": len(labelled),
    }
    return recall, precision


def marker_kind(marker: str | None) -> str | None:
    if not marker:
        return None
    if marker[0].isdigit():
        return "number"
    if marker[0].isalpha():
        return "letter"
    return "bullet"


def list_runs(result: Result) -> list[list[Block]]:
    runs: list[list[Block]] = []
    current: list[Block] = []
    for block in ordered(result):
        kind = marker_kind(block.get("marker")) if block["role"] == "listItem" else None
        if kind and current and current[-1]["page"] == block["page"] and marker_kind(current[-1].get("marker")) == kind:
            current.append(block)
            continue
        if current:
            runs.append(current)
        current = [block] if kind else []
    if current:
        runs.append(current)
    return runs


def list_scores(reference: list[dict[str, Any]], result: Result) -> tuple[Count, Count]:
    runs = list_runs(result)
    lists: Count = {"found": 0, "of": len(reference)}
    items: Count = {"found": 0, "of": sum(expected["items"] for expected in reference)}
    for expected in reference:
        anchor = comparable(expected["first_item"])
        run = next((run for run in runs if anchor in comparable(run[0]["text"])), None)
        if run is None or marker_kind(run[0].get("marker")) != expected["kind"]:
            continue
        items = {"found": items["found"] + min(len(run), expected["items"]), "of": items["of"]}
        lists = {"found": lists["found"] + (len(run) == expected["items"]), "of": lists["of"]}
    return lists, items


def link_scores(reference: list[dict[str, Any]], result: Result) -> Count:
    links = result.get("links") or []
    found = sum(
        1
        for expected in reference
        if any(comparable(link["text"]) == comparable(expected["text"]) and link["target"] == expected["target"] for link in links)
    )
    return {"found": found, "of": len(reference)}


def same_cell(expected: Any, text: str) -> bool:
    actual = normalise(text)
    if expected is None:
        return actual in EMPTY_CELL
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return float(NUMBER_DECORATION.sub("", actual)) == float(expected)
        except ValueError:
            return False
    return actual == normalise(str(expected))


def extracted_grid(result: Result, pages: list[int]) -> dict[tuple[int, int], Cell]:
    grid: dict[tuple[int, int], Cell] = {}
    offset = 0
    for table in sorted((table for table in result["tables"] if table["page"] in pages), key=lambda table: table["page"]):
        for cell in table["cells"]:
            grid.setdefault((offset + cell["row"], cell["column"]), cell)
        offset += 1 + max((cell["row"] for cell in table["cells"]), default=-1)
    return grid


def table_scores(entry: dict[str, Any], result: Result) -> tuple[Count, Count] | None:
    tables = expected_tables(entry)
    if not tables:
        return None
    cells: Count = {"found": 0, "of": 0}
    headers: Count = {"found": 0, "of": 0}
    for pages, expected in tables:
        grid = extracted_grid(result, pages)
        for cell in expected:
            found = grid.get((cell.row, cell.column))
            right = found is not None and same_cell(cell.value, found["text"])
            cells = {"found": cells["found"] + right, "of": cells["of"] + 1}
            if cell.header:
                labelled = right and found is not None and found["kind"] in HEADER_KINDS
                headers = {"found": headers["found"] + labelled, "of": headers["of"] + 1}
    return cells, headers


def locate(anchors: list[str], blocks: list[Block]) -> tuple[int, int, int, int] | None:
    wanted = [normalise(anchor) for anchor in anchors]
    best: tuple[int, int, int, int] | None = None
    for block in blocks:
        for line_number, line in enumerate(block["text"].split("\n")):
            for variant in (normalise(line), normalise(line[::-1])):
                for anchor in wanted:
                    at = variant.find(anchor)
                    if at >= 0:
                        spot = (block["page"], block["reading_order"], line_number, at)
                        if best is None or spot < best:
                            best = spot
    return best


def reading_order_score(anchors: list[dict[str, Any]], result: Result) -> Count:
    blocks = ordered(result)
    spots = [locate(item["anchors"], blocks) for item in anchors if item["anchors"]]
    pairs = list(itertools.combinations(spots, 2))
    found = sum(1 for first, second in pairs if first is not None and second is not None and first < second)
    return {"found": found, "of": len(pairs)}


def score(
    entry: dict[str, Any], result: Result, anchors: list[dict[str, Any]] | None, excluded: list[str] | None = None
) -> dict[str, Count]:
    scores: dict[str, Count] = {"text": text_score(entry, result, excluded)}
    if entry.get("headings_expected"):
        scores["headings"], scores["heading_precision"] = heading_scores(entry["headings_expected"], result)
    tables = table_scores(entry, result)
    if tables:
        scores["table_cells"], scores["header_cells"] = tables
    if anchors:
        scores["reading_order"] = reading_order_score(anchors, result)
    return scores


MIXED = re.compile(r"[A-Za-z\d]")


def logical_units(source: dict[str, Any]) -> list[str]:
    units: list[str] = []
    for section in source["right_column_read_first"] + source["left_column_read_second"]:
        units.append(section["heading"])
        units.extend(section["paragraphs"])
    return units


def unit_scores(source: dict[str, Any], result: Result) -> tuple[Count, Count]:
    text = normalise(document_text(result))
    units = [normalise(unit) for unit in logical_units(source)]
    mixed = [unit for unit in units if MIXED.search(unit)]
    return (
        {"found": sum(1 for unit in units if unit in text), "of": len(units)},
        {"found": sum(1 for unit in mixed if unit in text), "of": len(mixed)},
    )


def table_strings(entry: dict[str, Any], result: Result) -> Count:
    text = normalise(document_text(result))
    strings = [normalise(str(cell.value)) for _, cells in expected_tables(entry) for cell in cells if cell.value is not None]
    return {"found": sum(1 for string in strings if string in text), "of": len(strings)}


def primary_language(text: str | None) -> str | None:
    match = LANGUAGE_TAG.match((text or "").strip())
    return match.group(0).lower() if match else None


def field_scores(entry: dict[str, Any], values: dict[str, str | None]) -> dict[str, Count]:
    scores = {"title": coverage(entry["title_expected"], values.get("title") or "")}
    expected = primary_language(entry.get("language_expected"))
    if expected is not None:
        scores["language"] = {"found": int(expected == primary_language(values.get("language"))), "of": 1}
    return scores


def with_percent(count: Count) -> dict[str, Any]:
    percent = round(100 * count["found"] / count["of"], 1) if count["of"] else None
    return {"found": count["found"], "of": count["of"], "percent": percent}


def target_from(best: Fraction) -> int:
    return math.floor((best + 100) / 2)


def targets(baseline: dict[str, Any]) -> dict[str, Any]:
    samples: dict[str, dict[str, Any]] = {}
    for sample, tools in baseline["samples"].items():
        metrics: dict[str, Any] = {}
        for metric in TARGET_METRICS:
            fixed = FIXED_TARGETS.get((sample, metric))
            if fixed is not None and any(metric in scores for scores in tools.values()):
                metrics[metric] = {"target": fixed, "from": "fixed"}
                continue
            percents = [Fraction(100 * s[metric]["found"], s[metric]["of"]) for s in tools.values() if metric in s and s[metric]["of"]]
            if percents:
                best = max(percents)
                metrics[metric] = {"target": target_from(best), "from": "formula", "zero_baseline": best == 0}
        for (fixed_sample, metric), value in FIXED_TARGETS.items():
            if fixed_sample == sample and metric not in metrics:
                metrics[metric] = {"target": value, "from": "fixed"}
        samples[sample] = metrics
    return {"rule": RULE, "baseline": "eval/baseline.json", "samples": samples}
