import json
from pathlib import Path
from typing import Any

from core.extract import service_dict
from core.extract.shapes import Result
from core.scan.lines import Line, tesseract_lines

ROOT = Path(__file__).resolve().parent.parent.parent
SERVICE = ROOT / "eval" / "fixtures" / "cu" / "prebuilt-layout"
TESSERACT = ROOT / "eval" / "fixtures" / "tesseract"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class RecordedProvider:
    name = "recorded"

    def __init__(self, fixtures: Path = SERVICE) -> None:
        self.fixtures = fixtures

    def read(self, path: Path) -> Result:
        return service_dict.read(load(self.fixtures / f"{path.name[:2]}.json"))


def recorded_scan_lines(path: Path, pages: list[int]) -> list[Line]:
    fixture = TESSERACT / f"{path.name[:2]}.json"
    if not fixture.is_file():
        return []
    return [line for page in load(fixture)["pages"] if page["number"] in pages for line in tesseract_lines(page)]
