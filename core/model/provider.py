from pathlib import Path
from typing import Protocol

from core.extract.shapes import Result


class Provider(Protocol):
    name: str

    def read(self, path: Path) -> Result: ...
