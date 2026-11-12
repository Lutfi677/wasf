import pytest

from core.scan import crosscheck
from core.scan.lines import Line, service_lines, tesseract_lines


def line_of(source: str, text: str, top: float, confidence: float = 99.0, page: int = 1, left: float = 0.1, right: float = 0.9) -> Line:
    return {
        "source": source,
        "page": page,
        "box": [left, top, right, top + 0.02],
        "words": [{"text": word, "confidence": confidence} for word in text.split()],
    }


def test_matching_confident_lines_with_the_same_digits_give_no_region():
    first = [line_of("tesseract", "Total 12 345", 0.3)]
    second = [line_of("service", "Total 12 345", 0.3)]
    assert crosscheck.route(first, second) == []


def test_low_confidence_in_one_source_gives_a_region_with_that_reason():
    first = [line_of("tesseract", "Total 12 345", 0.3, confidence=60)]
    second = [line_of("service", "Total 12 345", 0.3)]
    regions = crosscheck.route(first, second)
    assert [region["reasons"] for region in regions] == [["low_confidence_tesseract"]]
    assert regions[0]["page"] == 1


def test_a_line_only_one_source_has_goes_to_a_person():
    first = [line_of("tesseract", "Total 12 345", 0.3), line_of("tesseract", "Extra 99", 0.5)]
    second = [line_of("service", "Total 12 345", 0.3)]
    assert [region["reasons"] for region in crosscheck.route(first, second)] == [["not_in_service"]]
    first = [line_of("tesseract", "Total 12 345", 0.3)]
    second = [line_of("service", "Total 12 345", 0.3), line_of("service", "Extra 99", 0.5)]
    assert [region["reasons"] for region in crosscheck.route(first, second)] == [["not_in_tesseract"]]


def test_confident_sources_that_disagree_on_digits_go_to_a_person():
    first = [line_of("tesseract", "Parcel 14-203-007", 0.5)]
    second = [line_of("service", "Parcel 14-201-007", 0.5)]
    assert [region["reasons"] for region in crosscheck.route(first, second)] == [["digits_differ"]]


def test_lines_split_differently_are_compared_as_one_region():
    first = [line_of("tesseract", "Total 12 345", 0.3)]
    second = [line_of("service", "Total 12", 0.3, right=0.4), line_of("service", "345", 0.3, left=0.5)]
    assert crosscheck.route(first, second) == []


def test_lines_on_different_pages_do_not_match():
    first = [line_of("tesseract", "Total 12", 0.3, page=1)]
    second = [line_of("service", "Total 12", 0.3, page=2)]
    reasons = sorted(reason for region in crosscheck.route(first, second) for reason in region["reasons"])
    assert reasons == ["not_in_service", "not_in_tesseract"]


def test_lines_on_different_rows_do_not_match():
    first = [line_of("tesseract", "Total 12", 0.3)]
    second = [line_of("service", "Total 12", 0.5)]
    assert len(crosscheck.route(first, second)) == 2


def test_regions_are_ordered_by_page_then_position():
    first = [line_of("tesseract", "B 2", 0.6), line_of("tesseract", "A 1", 0.2), line_of("tesseract", "C 3", 0.1, page=2)]
    regions = crosscheck.route(first, [])
    assert [(region["page"], round(region["box"][1], 2)) for region in regions] == [(1, 0.2), (1, 0.6), (2, 0.1)]


def test_a_region_covers_the_lines_it_joins():
    first = [line_of("tesseract", "Total 12", 0.3, confidence=10, left=0.2, right=0.6)]
    second = [line_of("service", "Total 12", 0.3, left=0.1, right=0.5)]
    (region,) = crosscheck.route(first, second)
    assert region["box"] == pytest.approx([0.1, 0.3, 0.6, 0.32])


def test_tesseract_words_are_grouped_into_lines_and_scaled_to_the_page():
    page = {
        "number": 3,
        "width": 1000,
        "height": 2000,
        "data": {
            "text": ["Hello", " ", "world", "next", "lost"],
            "conf": ["96", "-1", "88.5", "70", "-1"],
            "block_num": [1, 1, 1, 1, 1],
            "par_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 2, 2],
            "left": [100, 0, 300, 100, 0],
            "top": [200, 0, 210, 400, 0],
            "width": [150, 0, 200, 80, 0],
            "height": [40, 0, 30, 40, 0],
        },
    }
    first, second = tesseract_lines(page)
    assert first["source"] == "tesseract"
    assert first["page"] == 3
    assert first["box"] == pytest.approx([0.1, 0.1, 0.5, 0.12])
    assert [(word["text"], word["confidence"]) for word in first["words"]] == [("Hello", 96.0), ("world", 88.5)]
    assert [word["text"] for word in second["words"]] == ["next"]


def test_service_lines_take_their_words_by_span_and_scale_confidence_to_percent():
    response = {
        "contents": [
            {
                "pages": [
                    {
                        "pageNumber": 1,
                        "width": 10.0,
                        "height": 20.0,
                        "lines": [
                            {"content": "one two", "source": "D(1,1,2,3,2,3,4,1,4)", "span": {"offset": 0, "length": 7}},
                            {"content": "three", "source": "D(1,1,6,3,6,3,8,1,8)", "span": {"offset": 8, "length": 5}},
                            {"content": "none", "source": None, "span": {"offset": 14, "length": 4}},
                        ],
                        "words": [
                            {"content": "one", "span": {"offset": 0, "length": 3}, "confidence": 0.99},
                            {"content": "two", "span": {"offset": 4, "length": 3}, "confidence": 0.5},
                            {"content": "three", "span": {"offset": 8, "length": 5}},
                        ],
                    }
                ]
            }
        ]
    }
    first, second = service_lines(response)
    assert first["box"] == pytest.approx([0.1, 0.1, 0.3, 0.2])
    assert [(word["text"], round(word["confidence"], 1)) for word in first["words"]] == [("one", 99.0), ("two", 50.0)]
    assert second["words"] == [{"text": "three", "confidence": 0.0}]
