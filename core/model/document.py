import math
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

BOX_TOLERANCE = 2.0


def check_box(box: list[float]) -> list[float]:
    if len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise ValueError("a box has four finite numbers")
    if box[0] > box[2] or box[1] > box[3]:
        raise ValueError("a box runs left to right and top to bottom")
    return box


Box = Annotated[list[float], AfterValidator(check_box)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Strict):
    number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Block(Strict):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    role: str | None = None
    text: str
    box: Box | None = None
    reading_order: int = Field(ge=0)
    engine: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=100)
    language: str | None = None
    level: int | None = Field(default=None, ge=1)
    marker: str | None = None


class Cell(Strict):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    text: str
    kind: str = Field(min_length=1)
    box: Box | None = None


class Table(Strict):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    cells: list[Cell] = Field(min_length=1)


class Link(Strict):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    box: Box
    text: str
    target: str | None = None


class Figure(Strict):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    box: Box
    caption: str | None = None


class Region(Strict):
    page: int = Field(ge=1)
    box: Box
    reasons: list[str] = Field(min_length=1)


def check_inside(box: list[float] | None, page: Page, what: str) -> None:
    if box is None:
        return
    if box[0] < -BOX_TOLERANCE or box[1] < -BOX_TOLERANCE or box[2] > page.width + BOX_TOLERANCE or box[3] > page.height + BOX_TOLERANCE:
        raise ValueError(f"{what} lies outside page {page.number}")


class Document(Strict):
    language: str | None = None
    engines: list[str] = Field(min_length=1)
    pages: list[Page] = Field(min_length=1)
    blocks: list[Block] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_whole(self) -> Self:
        if [page.number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("pages are numbered 1 to n in order")
        if [block.reading_order for block in self.blocks] != list(range(len(self.blocks))):
            raise ValueError("reading order runs from 0 with no gaps, in list order")
        ids = [item.id for item in (*self.blocks, *self.tables, *self.links, *self.figures)]
        if len(set(ids)) != len(ids):
            raise ValueError("ids are not unique")
        sizes = {page.number: page for page in self.pages}
        for item in (*self.blocks, *self.tables, *self.links, *self.figures, *self.regions):
            if item.page not in sizes:
                raise ValueError(f"page {item.page} is not in the document")
        for item in (*self.blocks, *self.links, *self.figures, *self.regions):
            check_inside(item.box, sizes[item.page], type(item).__name__.lower())
        for table in self.tables:
            places = [(cell.row, cell.column) for cell in table.cells]
            if len(set(places)) != len(places):
                raise ValueError(f"table {table.id} has two cells in one place")
            for cell in table.cells:
                check_inside(cell.box, sizes[table.page], "cell")
        return self
