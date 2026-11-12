from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.extract import service_dict
from core.extract.shapes import Result

Analyze = Callable[[bytes], tuple[dict[str, Any], dict[str, Any], float]]


class ContentUnderstandingProvider:
    name = "content-understanding"

    def __init__(self, analyze: Analyze) -> None:
        self.analyze = analyze
        self.calls: list[dict[str, Any]] = []

    def read(self, path: Path) -> Result:
        response, usage, seconds = self.analyze(path.read_bytes())
        self.calls.append({"usage": usage, "seconds": seconds})
        return service_dict.read(response)
