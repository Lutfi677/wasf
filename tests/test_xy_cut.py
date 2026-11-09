from core.extract.shapes import Block
from core.order import xy_cut


def block(name: str, box: list[float] | None, page: int = 1, order: int = 0) -> Block:
    return {"id": name, "page": page, "role": None, "text": name, "box": box, "reading_order": order, "engine": "test", "confidence": None}


def names(blocks: list[Block]) -> list[str]:
    return [b["id"] for b in blocks]


def two_columns(header: str, left: tuple[str, str], right: tuple[str, str]) -> list[Block]:
    return [
        block(right[1], [300, 140, 500, 150]),
        block(left[0], [50, 100, 250, 110]),
        block(header, [100, 50, 450, 70]),
        block(right[0], [300, 100, 500, 110]),
        block(left[1], [50, 140, 250, 150]),
        block("footer", [200, 700, 350, 710]),
    ]


def test_columns_are_read_left_to_right_under_a_full_width_header():
    ordered = xy_cut.order(two_columns("Title", ("L1", "L2"), ("R1", "R2")))
    assert names(ordered) == ["Title", "L1", "L2", "R1", "R2", "footer"]
    assert [b["reading_order"] for b in ordered] == list(range(6))


def test_columns_are_read_right_to_left_on_an_arabic_page():
    ordered = xy_cut.order(two_columns("عنوان", ("يسار١", "يسار٢"), ("يمين١", "يمين٢")))
    assert names(ordered) == ["عنوان", "يمين١", "يمين٢", "يسار١", "يسار٢", "footer"]


def test_two_cells_in_one_row_follow_the_page_direction():
    row = [block("تاريخ", [50, 100, 150, 110]), block("رقم", [400, 100, 500, 110])]
    assert names(xy_cut.order(row)) == ["رقم", "تاريخ"]
    latin = [block("number", [400, 100, 500, 110]), block("date", [50, 100, 150, 110])]
    assert names(xy_cut.order(latin)) == ["date", "number"]


def test_pages_stay_in_order_and_blocks_without_a_box_go_last_on_their_page():
    blocks = [block("p2", [50, 50, 100, 60], page=2), block("nobox", None), block("p1", [50, 50, 100, 60])]
    assert names(xy_cut.order(blocks)) == ["p1", "nobox", "p2"]


def test_free_gaps_merge_overlapping_spans():
    assert xy_cut.free_gaps([(0, 10), (5, 20), (30, 40), (38, 50)]) == [(20, 30)]
