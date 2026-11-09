from typing import NotRequired, TypedDict


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
