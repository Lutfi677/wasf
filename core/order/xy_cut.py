from core.extract.shapes import Block
from core.text.arabic_letters import is_mostly_arabic

COLUMN_GAP = 10.0
ROW_GAP = 0.5
EDGE = 0.5

Gap = tuple[float, float]


def free_gaps(spans: list[Gap]) -> list[Gap]:
    ordered = sorted(spans)
    gaps: list[Gap] = []
    reach = ordered[0][1]
    for start, end in ordered[1:]:
        if start > reach:
            gaps.append((reach, start))
        reach = max(reach, end)
    return gaps


def widest(gaps: list[Gap], minimum: float) -> Gap | None:
    wide = [gap for gap in gaps if gap[1] - gap[0] >= minimum]
    return max(wide, key=lambda gap: gap[1] - gap[0]) if wide else None


def box_of(block: Block) -> list[float]:
    box = block["box"]
    if box is None:
        raise ValueError(f"block {block['id']} has no box")
    return box


def cut(blocks: list[Block], right_to_left: bool) -> list[Block]:
    if len(blocks) < 2:
        return list(blocks)
    column = widest(free_gaps([(box_of(b)[0], box_of(b)[2]) for b in blocks]), COLUMN_GAP)
    if column is not None:
        first = [b for b in blocks if box_of(b)[2] <= column[0] + EDGE]
        second = [b for b in blocks if box_of(b)[2] > column[0] + EDGE]
        if right_to_left:
            first, second = second, first
        return cut(first, right_to_left) + cut(second, right_to_left)
    row = widest(free_gaps([(box_of(b)[1], box_of(b)[3]) for b in blocks]), ROW_GAP)
    if row is not None:
        top = [b for b in blocks if box_of(b)[3] <= row[0] + EDGE]
        bottom = [b for b in blocks if box_of(b)[3] > row[0] + EDGE]
        return cut(top, right_to_left) + cut(bottom, right_to_left)
    return sorted(blocks, key=lambda b: (box_of(b)[1], -box_of(b)[2] if right_to_left else box_of(b)[0]))


def order(blocks: list[Block]) -> list[Block]:
    arranged: list[Block] = []
    for page in sorted({block["page"] for block in blocks}):
        on_page = [block for block in blocks if block["page"] == page]
        right_to_left = is_mostly_arabic(" ".join(block["text"] for block in on_page))
        boxed = [block for block in on_page if block["box"] is not None]
        arranged.extend(cut(boxed, right_to_left) + [block for block in on_page if block["box"] is None])
    renumbered: list[Block] = []
    for position, block in enumerate(arranged):
        copy = block.copy()
        copy["reading_order"] = position
        renumbered.append(copy)
    return renumbered
