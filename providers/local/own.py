from collections.abc import Callable
from pathlib import Path

from core.detectors.scan import detect_image_only
from core.extract.shapes import Result
from core.order import xy_cut
from core.scan.lines import Line
from core.structure import blocks

ScanReader = Callable[[Path, list[int]], list[Line]]


class LocalProvider:
    name = "local"

    def __init__(self, scan_reader: ScanReader | None = None) -> None:
        self.scan_reader = scan_reader

    def read(self, path: Path) -> Result:
        result = blocks.structure(path)
        result["blocks"] = xy_cut.order(result["blocks"])
        scans = sorted(finding.page for finding in detect_image_only(path) if finding.page is not None)
        result["scan_pages"] = scans
        result["lines"] = self.scan_reader(path, scans) if scans and self.scan_reader is not None else []
        return result
