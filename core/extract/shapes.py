from typing import NotRequired, TypedDict

from core.scan.lines import Line as ScanLine


class Block(TypedDict):
    id: str
    page: int
    role: str | None
    text: str
    box: list[float] | None
    reading_order: int
    engine: str
    confidence: float | None
    level: NotRequired[int]
    marker: NotRequired[str]


class Cell(TypedDict):
    row: int
    column: int
    text: str
    kind: str
    box: NotRequired[list[float]]


class Table(TypedDict):
    id: str
    page: int
    cells: list[Cell]


class Link(TypedDict):
    id: str
    page: int
    box: list[float]
    text: str
    target: str | None


class Figure(TypedDict):
    id: str
    page: int
    box: list[float]
    caption: str | None


class Page(TypedDict):
    number: int
    width: float
    height: float


class Result(TypedDict):
    engine: str
    version: str
    pages: list[Page]
    blocks: list[Block]
    tables: list[Table]
    links: NotRequired[list[Link]]
    figures: NotRequired[list[Figure]]
    lines: NotRequired[list[ScanLine]]
    scan_pages: NotRequired[list[int]]
