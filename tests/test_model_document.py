from typing import Any

import pytest
from pydantic import ValidationError

from core.model.document import Document


def page(number: int = 1) -> dict[str, Any]:
    return {"number": number, "width": 612.0, "height": 792.0}


def block(order: int = 0, **changes: Any) -> dict[str, Any]:
    found: dict[str, Any] = {
        "id": f"b{order}",
        "page": 1,
        "text": "Hello",
        "box": [10.0, 10.0, 100.0, 30.0],
        "reading_order": order,
        "engine": "x",
    }
    found.update(changes)
    return found


def cell(row: int, column: int) -> dict[str, Any]:
    return {"row": row, "column": column, "text": "a", "kind": "content"}


def document(**changes: Any) -> dict[str, Any]:
    found: dict[str, Any] = {"engines": ["x"], "pages": [page(1), page(2)], "blocks": [block(0), block(1, page=2)]}
    found.update(changes)
    return found


def test_a_valid_document_validates_and_round_trips():
    validated = Document.model_validate(document())
    assert Document.model_validate(validated.model_dump()) == validated


def test_optional_fields_default_to_nothing():
    validated = Document.model_validate(document())
    first = validated.blocks[0]
    assert (first.role, first.confidence, first.language, first.level, first.marker) == (None, None, None, None, None)
    assert (validated.tables, validated.links, validated.figures, validated.regions) == ([], [], [], [])


def test_a_document_may_have_tables_links_figures_and_regions():
    validated = Document.model_validate(document(
        tables=[{"id": "t0", "page": 1, "cells": [cell(0, 0), cell(0, 1)]}],
        links=[{"id": "l0", "page": 1, "box": [0, 0, 5, 5], "text": "here", "target": "https://example.org"}],
        figures=[{"id": "f0", "page": 2, "box": [0, 0, 50, 50], "caption": None}],
        regions=[{"page": 2, "box": [0, 0, 612, 100], "reasons": ["low_confidence_tesseract"]}],
    ))
    assert len(validated.tables[0].cells) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"pages": [page(2)]},
        {"pages": [page(1), page(3)]},
        {"pages": []},
        {"engines": []},
        {"blocks": [block(1)]},
        {"blocks": [block(0), block(0, id="b1")]},
        {"blocks": [block(0), block(1, id="b0")]},
        {"blocks": [block(0, page=3)]},
        {"blocks": [block(0, page=0)]},
        {"blocks": [block(0, box=[10, 10, 700, 30])]},
        {"blocks": [block(0, box=[100, 10, 10, 30])]},
        {"blocks": [block(0, box=[1, 2, 3])]},
        {"blocks": [block(0, box=[float("nan"), 0, 1, 1])]},
        {"blocks": [block(0, confidence=101)]},
        {"blocks": [block(0, surprise=1)]},
        {"blocks": [block(0, level=0)]},
        {"tables": [{"id": "t", "page": 1, "cells": []}]},
        {"tables": [{"id": "t", "page": 1, "cells": [cell(0, 0), cell(0, 0)]}]},
        {"tables": [{"id": "t", "page": 5, "cells": [cell(0, 0)]}]},
        {"links": [{"id": "l", "page": 9, "box": [0, 0, 1, 1], "text": "x"}]},
        {"regions": [{"page": 1, "box": [0, 0, 10, 10], "reasons": []}]},
        {"regions": [{"page": 1, "box": [0, 0, 10, 900], "reasons": ["x"]}]},
    ],
)
def test_invalid_documents_are_refused(changes):
    with pytest.raises(ValidationError):
        Document.model_validate(document(**changes))


def test_a_box_a_little_outside_the_page_is_tolerated():
    Document.model_validate(document(blocks=[block(0, box=[-1.0, 0.0, 613.5, 792.0])]))
