from fractions import Fraction

import pytest

scoring = pytest.importorskip("scoring")


def block(text, reading_order, page=1, role=None):
    return {
        "id": f"t-{reading_order}",
        "page": page,
        "role": role,
        "text": text,
        "box": None,
        "reading_order": reading_order,
        "engine": "test",
        "confidence": None,
    }


def result(blocks, tables=()):
    return {"engine": "test", "version": "0", "pages": [], "blocks": list(blocks), "tables": list(tables)}


def test_normalise_folds_space_and_presentation_forms():
    assert scoring.normalise("  a\n\tb  ") == "a b"
    assert scoring.normalise("ﺍﻟ") == "ال"
    assert scoring.normalise("Out-of-\ndistrict") == "Out-of-district"


def test_comparable_ignores_case():
    assert scoring.comparable("CALL TO ORDER") == scoring.comparable("Call to Order")


def test_coverage_is_full_for_the_same_text_and_zero_for_nothing():
    assert scoring.coverage("one two three", "one  two\nthree") == {"found": 13, "of": 13}
    assert scoring.coverage("one two three", "") == {"found": 0, "of": 13}


def test_key_strings_drop_structure_notes_and_numbers():
    entry = {
        "headings_expected": [{"level": 1, "text": "Fees"}],
        "tables_expected": [{"page": 1, "header_row": ["Program (rowspan 2)", "Cost"], "rows": [["Nursing", "$45"]]}],
    }
    assert scoring.key_strings(entry) == ["fees", "program", "cost", "nursing"]


def test_excluded_key_strings_leave_the_text_reference():
    entry = {"headings_expected": [{"level": 1, "text": "Minutes, March 12"}, {"level": 2, "text": "Roll Call"}]}
    assert scoring.key_strings(entry, ["MINUTES, March 12"]) == ["roll call"]
    assert scoring.text_score(entry, result([block("ROLL CALL", 0)]), ["Minutes, March 12"]) == {"found": 1, "of": 1}


def test_key_strings_score_counts_whole_strings():
    entry = {"headings_expected": [{"level": 1, "text": "Roll Call"}, {"level": 2, "text": "Adjournment"}]}
    assert scoring.text_score(entry, result([block("ROLL CALL", 0), block("Present: all", 1)])) == {"found": 1, "of": 2}


def test_scan_text_is_scored_per_page():
    entry = {"ground_truth_text_per_page": ["abc", "de"]}
    assert scoring.text_score(entry, result([block("abc", 0, page=1), block("xx", 1, page=2)])) == {"found": 3, "of": 5}


def test_headings_need_a_heading_role():
    expected = [{"level": 1, "text": "Annual Report"}, {"level": 2, "text": "Summary"}]
    unlabelled = result([block("Annual Report", 0), block("Summary", 1)])
    labelled = result([block("Annual", 0, role="title"), block("Report", 1, role="title"), block("Summary", 2, role="heading")])
    assert scoring.heading_scores(expected, unlabelled) == ({"found": 0, "of": 2}, {"found": 0, "of": 0})
    assert scoring.heading_scores(expected, labelled) == ({"found": 2, "of": 2}, {"found": 3, "of": 3})


def test_heading_runs_do_not_cross_a_body_block():
    expected = [{"level": 1, "text": "Annual Report"}]
    split = result([block("Annual", 0, role="title"), block("body", 1), block("Report", 2, role="title")])
    assert scoring.heading_scores(expected, split)[0] == {"found": 0, "of": 1}


def test_expected_cells_skip_merged_categories():
    table = {
        "pages": [1],
        "header_rows": [["Category", "Program", "Fee"]],
        "row_header_columns": ["Category", "Program"],
        "rows": [
            {"category": "Health", "program": "Nursing", "fee": 45},
            {"category": "Health", "program": "Dental", "fee": None},
        ],
    }
    cells = scoring.expected_cells(table)
    assert [(c.row, c.column) for c in cells] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 1), (2, 2)]
    assert [c.header for c in cells] == [True, True, True, True, True, False, True, False]


def test_same_cell_reads_currency_and_dashes():
    assert scoring.same_cell(118, "$118")
    assert scoring.same_cell(None, "—")
    assert scoring.same_cell("Change (%)", "Change  (%)")
    assert not scoring.same_cell(118, "$119")


def test_tables_split_over_pages_are_joined_in_row_order():
    entry = {"tables_expected": [{"pages": [1, 2], "header_row": ["Item", "Cost"], "rows": [["Tea", "$2"], ["Cake", "$3"]]}]}
    first = {"id": "a", "page": 1, "cells": [
        {"row": 0, "column": 0, "text": "Item", "kind": "columnHeader"},
        {"row": 0, "column": 1, "text": "Cost", "kind": "content"},
        {"row": 1, "column": 0, "text": "Tea", "kind": "content"},
        {"row": 1, "column": 1, "text": "$2", "kind": "content"},
    ]}
    second = {"id": "b", "page": 2, "cells": [
        {"row": 0, "column": 0, "text": "Cake", "kind": "content"},
        {"row": 0, "column": 1, "text": "$3", "kind": "content"},
    ]}
    cells, headers = scoring.table_scores(entry, result([], [second, first]))
    assert cells == {"found": 6, "of": 6}
    assert headers == {"found": 1, "of": 2}


def test_no_tables_found_scores_zero():
    entry = {"tables_expected": [{"page": 1, "header_row": ["Item"], "rows": [["Tea"]]}]}
    assert scoring.table_scores(entry, result([block("Item Tea", 0)])) == ({"found": 0, "of": 2}, {"found": 0, "of": 1})


ANCHORS = [
    {"key": "first", "anchors": ["Alpha"]},
    {"key": "picture", "anchors": []},
    {"key": "second", "anchors": ["Beta"]},
    {"key": "third", "anchors": ["Gamma", "Delta"]},
]


def test_reading_order_counts_pairs_in_the_right_order():
    right = result([block("Alpha one", 0), block("Beta two", 1), block("Delta\nGamma", 2)])
    swapped = result([block("Beta two", 0), block("Alpha one", 1), block("Gamma", 2)])
    assert scoring.reading_order_score(ANCHORS, right) == {"found": 3, "of": 3}
    assert scoring.reading_order_score(ANCHORS, swapped) == {"found": 2, "of": 3}


def test_reading_order_loses_pairs_with_a_missing_block():
    assert scoring.reading_order_score(ANCHORS, result([block("Alpha", 0), block("Gamma", 1)])) == {"found": 1, "of": 3}


def test_reading_order_uses_page_before_position():
    later_page = result([block("Beta", 0, page=2), block("Alpha", 1, page=1), block("Gamma", 2, page=2)])
    assert scoring.reading_order_score(ANCHORS, later_page) == {"found": 3, "of": 3}


def test_anchor_is_found_in_a_line_stored_in_visual_order():
    logical = "أولا"
    visual = "ﻻﻭﺃ"
    assert scoring.normalise(visual[::-1]) == logical
    assert scoring.locate([logical], [block(visual, 0)]) == (1, 0, 0, 0)


def test_primary_language_reads_the_first_tag():
    assert scoring.primary_language("en-US") == "en"
    assert scoring.primary_language("ar (document), with en spans") == "ar"
    assert scoring.primary_language("Arabic") is None
    assert scoring.primary_language(None) is None


def test_field_scores_cover_title_and_language():
    entry = {"title_expected": "Annual Report", "language_expected": "en-US"}
    assert scoring.field_scores(entry, {"title": "Annual Report", "language": "en"}) == {
        "title": {"found": 13, "of": 13},
        "language": {"found": 1, "of": 1},
    }
    assert scoring.field_scores(entry, {"title": None, "language": "ar"})["language"] == {"found": 0, "of": 1}


def test_language_is_not_scored_without_a_single_tag_in_the_key():
    entry = {"title_expected": "Form", "language_expected": "bilingual en/ar: tag every label"}
    assert set(scoring.field_scores(entry, {"title": "Form", "language": "ar"})) == {"title"}


def test_target_is_half_the_gap_rounded_down():
    assert scoring.target_from(Fraction(0)) == 50
    assert scoring.target_from(Fraction(941, 10)) == 97
    assert scoring.target_from(Fraction(100)) == 100
    assert scoring.target_from(Fraction(1, 3) * 100) == 66


def test_targets_take_the_best_tool_and_apply_fixed_rules():
    baseline = {"samples": {
        "01": {
            "a": {"text": {"found": 1, "of": 4}, "header_cells": {"found": 0, "of": 4}, "heading_precision": {"found": 0, "of": 0}},
            "b": {"text": {"found": 3, "of": 4}, "header_cells": {"found": 0, "of": 4}},
        },
        "05": {"a": {"text": {"found": 0, "of": 10}}},
    }}
    samples = scoring.targets(baseline)["samples"]
    assert samples["01"] == {
        "text": {"target": 87, "from": "formula", "zero_baseline": False},
        "header_cells": {"target": 100, "from": "fixed"},
    }
    assert samples["05"] == {
        "text": {"target": 50, "from": "formula", "zero_baseline": True},
        "parcel_lines_to_person": {"target": 100, "from": "fixed"},
    }
