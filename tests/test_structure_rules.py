import pathlib

import pytest

from core.extract.pdf_lines import Char, Line
from core.structure import blocks, headings, links, lists

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "eval" / "samples"
WIDTH = 5.0


def line(text: str, left: float, top: float, size: float = 10.0, bold: bool = False, page: int = 1, group: int = 0) -> Line:
    chars: list[Char] = []
    x = left
    for character in text:
        chars.append({"text": character, "box": [x, top, x + WIDTH, top + size]})
        x += WIDTH
    return {"page": page, "group": group, "text": text, "box": [left, top, x, top + size], "size": size, "bold": bold, "chars": chars}


def marker(item: Line, glyphs: list[lists.Glyph], alone: dict[int, tuple[str, str]], lines: list[Line]) -> lists.Found:
    found = lists.marker_of(item, glyphs, alone, lines)
    assert found is not None
    return found


def test_body_size_is_the_size_with_most_characters():
    lines = [line("Title", 50, 10, size=20), line("A long body line of text", 50, 40), line("More body", 50, 55)]
    assert headings.body_size(lines) == 10.0


@pytest.mark.parametrize(("text", "size", "bold", "expected"), [
    ("Annual Report", 14.0, False, True),
    ("Roll Call", 10.0, True, True),
    ("Roll Call", 10.0, False, False),
    ("Important:", 10.0, True, False),
    ("Written comments are due.", 14.0, True, False),
    ("one two three four five six seven eight nine ten eleven twelve thirteen", 14.0, True, False),
    ("Total", 9.0, True, False),
])
def test_heading_candidates(text, size, bold, expected):
    assert headings.is_candidate(line(text, 50, 10, size=size, bold=bold), 10.0) is expected


def test_heading_levels_rank_sizes_largest_first():
    lines = [line("Report", 50, 10, size=24), line("Summary", 50, 40, size=14, bold=True), line("Body text here", 50, 60),
             line("Notes", 50, 80, size=14, bold=True)]
    assert headings.heading_levels(lines, set()) == {0: 1, 1: 2, 3: 2}


def test_number_and_letter_markers_at_the_start_of_a_line():
    numbered = line("1. Withdraw early", 60, 10)
    assert marker(numbered, [], {}, [numbered])[:4] == ("1.", "number", "1.", 60 + 3 * WIDTH)
    lettered = line("a) Minutes", 60, 10)
    assert marker(lettered, [], {}, [lettered])[1] == "letter"
    assert lists.marker_of(line("3.1 acres of land", 60, 10), [], {}, []) is None
    assert lists.marker_of(line("A resident spoke", 60, 10), [], {}, []) is None


def test_bullet_taken_from_a_glyph_beside_the_line():
    item = line("Road works", 78, 100)
    glyph = ("•", [60.0, 102.0, 64.0, 106.0])
    assert lists.marker_of(item, [glyph], {}, [item]) == ("•", "bullet", "", 78, None)
    far = ("•", [10.0, 102.0, 14.0, 106.0])
    assert lists.marker_of(item, [far], {}, [item]) is None


def test_unmapped_glyph_at_the_start_is_a_bullet_when_the_glyph_is_there():
    item = line("(cid:127) Wed 4:00 PM", 58, 100)
    glyph = ("•", [58.6, 102.0, 62.6, 106.0])
    assert marker(item, [glyph], {}, [item])[:3] == ("•", "bullet", "(cid:127)")
    assert lists.marker_of(item, [], {}, [item]) is None


def test_marker_on_a_line_of_its_own_marks_the_line_beside_it():
    marker = line("1.", 60, 100)
    item = line("Jordan spoke", 78, 100)
    lines = [marker, item]
    alone = {0: ("1.", "number")}
    assert lists.marker_of(item, [], alone, lines) == ("1.", "number", "", 78, 0)


def test_items_keep_their_indented_continuation_lines():
    lines = [
        line("1. First item that wraps", 60, 100),
        line("onto a second line", 75, 112),
        line("2. Second item", 60, 124),
        line("Body text after the list", 50, 140),
    ]
    items = lists.find_items(lines, {})
    assert [(item.lines, item.marker) for item in items] == [([0, 1], "1."), ([2], "2.")]


def test_build_makes_headings_list_items_and_body_blocks():
    lines = [
        line("Payment options", 50, 80, size=12, bold=True),
        line("1.", 60, 100),
        line("Pay online", 78, 100),
        line("2. Pay in person", 60, 114),
        line("Fees are due on the first day of the term and are charged per credit hour.", 50, 140),
    ]
    built = blocks.build(lines, {})
    assert [(b["role"], b["text"], b.get("marker"), b.get("level")) for b in built] == [
        ("heading", "Payment options", None, 1),
        ("listItem", "Pay online", "1.", None),
        ("listItem", "Pay in person", "2.", None),
        (None, "Fees are due on the first day of the term and are charged per credit hour.", None, None),
    ]
    assert [b["reading_order"] for b in built] == [0, 1, 2, 3]


def test_link_text_is_the_characters_inside_its_rectangle():
    lines = [line("To read it, click here.", 50, 100)]
    box = [50 + 12 * WIDTH, 99.0, 50 + 22 * WIDTH, 111.0]
    assert links.visible_text(lines, 1, box) == "click here"
    assert links.visible_text(lines, 2, box) == ""


def generated():
    if not (SAMPLES / "answer_key" / "manifest.json").is_file():
        pytest.skip("eval/samples has not been generated")


def test_done_when_fake_headings_and_lists_on_01_and_02_are_found():
    generated()
    run_rules = pytest.importorskip("run_rules")
    reference = run_rules.load(run_rules.REFERENCE)
    for entry in run_rules.load(run_rules.MANIFEST)["documents"][:2]:
        record = run_rules.score_sample(entry, reference[pathlib.PurePosixPath(entry["file"]).name])
        for metric in ("headings", "lists", "list_items"):
            assert record[metric]["found"] == record[metric]["of"], (entry["file"], metric)
    assert sum(len(reference[name]["lists"]) for name in list(reference)[:2]) == 5


def test_the_link_on_01_has_its_text_target_and_rectangle():
    generated()
    result = blocks.structure(SAMPLES / "pdfs" / "01_county_budget_summary.pdf")
    [link] = result.get("links") or []
    assert link["text"] == "click here"
    assert link["target"] == "https://www.example.org/riverbend/budget-2026"
    left, top, right, bottom = link["box"]
    page = result["pages"][link["page"] - 1]
    assert 0 <= left < right <= page["width"] and 0 <= top < bottom <= page["height"]
