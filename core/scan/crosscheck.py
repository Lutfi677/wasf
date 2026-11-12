from typing import TypedDict

from core.scan import line_rule
from core.scan.lines import Line, text_of

OVERLAP = 0.5
OTHER = {"tesseract": "service", "service": "tesseract"}


class Region(TypedDict):
    page: int
    box: list[float]
    reasons: list[str]


def digits(text: str) -> str:
    return "".join(character for character in text if character.isdigit())


def overlaps(first: Line, second: Line) -> bool:
    if first["page"] != second["page"]:
        return False
    left_a, top_a, right_a, bottom_a = first["box"]
    left_b, top_b, right_b, bottom_b = second["box"]
    shared = min(bottom_a, bottom_b) - max(top_a, top_b)
    smaller = min(bottom_a - top_a, bottom_b - top_b)
    return shared >= OVERLAP * smaller and min(right_a, right_b) > max(left_a, left_b)


def root(parents: list[int], index: int) -> int:
    while parents[index] != index:
        parents[index] = parents[parents[index]]
        index = parents[index]
    return index


def groups(first: list[Line], second: list[Line]) -> list[list[Line]]:
    lines = first + second
    parents = list(range(len(lines)))
    for i, line in enumerate(first):
        for j, other in enumerate(second):
            if overlaps(line, other):
                parents[root(parents, i)] = root(parents, len(first) + j)
    grouped: dict[int, list[Line]] = {}
    for index, line in enumerate(lines):
        grouped.setdefault(root(parents, index), []).append(line)
    return list(grouped.values())


def reading(group: list[Line], source: str) -> str:
    chosen = sorted((line for line in group if line["source"] == source), key=lambda line: (line["box"][1], line["box"][0]))
    return " ".join(text_of(line) for line in chosen)


def reasons(group: list[Line]) -> list[str]:
    sources = {line["source"] for line in group}
    found = {f"low_confidence_{line['source']}" for line in group if line_rule.goes_to_person(line)}
    if len(sources) == 1:
        found.add(f"not_in_{OTHER[next(iter(sources))]}")
    elif len({digits(reading(group, source)) for source in sources}) > 1:
        found.add("digits_differ")
    return sorted(found)


def union(group: list[Line]) -> list[float]:
    return [
        min(line["box"][0] for line in group),
        min(line["box"][1] for line in group),
        max(line["box"][2] for line in group),
        max(line["box"][3] for line in group),
    ]


def route(tesseract: list[Line], service: list[Line]) -> list[Region]:
    regions: list[Region] = []
    for group in groups(tesseract, service):
        found = reasons(group)
        if found:
            regions.append({"page": group[0]["page"], "box": union(group), "reasons": found})
    return sorted(regions, key=lambda region: (region["page"], region["box"][1], region["box"][0]))
