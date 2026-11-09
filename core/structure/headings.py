import collections

from core.extract.pdf_lines import Line

LARGER = 1.2
MAX_WORDS = 12
MAX_LEVEL = 6
CLOSING = (".", ",", ";", ":")


def body_size(lines: list[Line]) -> float:
    sizes: collections.Counter[float] = collections.Counter()
    for line in lines:
        sizes[line["size"]] += sum(1 for character in line["text"] if not character.isspace())
    return sizes.most_common(1)[0][0] if sizes else 0.0


def is_candidate(line: Line, body: float) -> bool:
    text = line["text"].strip()
    if not text or len(text.split()) > MAX_WORDS or text.endswith(CLOSING):
        return False
    return line["size"] >= body * LARGER or (line["bold"] and line["size"] >= body)


def heading_levels(lines: list[Line], excluded: set[int]) -> dict[int, int]:
    body = body_size(lines)
    candidates = [index for index, line in enumerate(lines) if index not in excluded and is_candidate(line, body)]
    sizes = sorted({lines[index]["size"] for index in candidates}, reverse=True)
    rank = {size: position + 1 for position, size in enumerate(sizes)}
    return {index: min(rank[lines[index]["size"]], MAX_LEVEL) for index in candidates}
