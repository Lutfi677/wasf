import os
import pathlib
import shutil
from typing import Any

import pypdfium2
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from core.scan.lines import Line, tesseract_lines

DPI = 200
SCALE: Any = DPI / 72
FILTER_SIZE = 3
PAGE_MODE = 3
DEFAULT_LANGUAGE = "eng"


class ToolMissing(RuntimeError):
    pass


def locate() -> str:
    candidate = os.environ.get("WASF_TESSERACT") or shutil.which("tesseract")
    if not candidate:
        raise ToolMissing("tesseract is not installed; install it or set WASF_TESSERACT")
    return candidate


def configure() -> str:
    pytesseract.pytesseract.tesseract_cmd = locate()
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    return str(pytesseract.get_tesseract_version())


def render(page: pypdfium2.PdfPage) -> Image.Image:
    return page.render(scale=SCALE).to_pil()


def prepare(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image).filter(ImageFilter.MedianFilter(FILTER_SIZE))


def options() -> str:
    found = f"--psm {PAGE_MODE}"
    tessdata = os.environ.get("WASF_TESSDATA")
    if tessdata:
        found += f' --tessdata-dir "{pathlib.Path(tessdata).as_posix()}"'
    return found


def recognise(image: Image.Image, language: str = DEFAULT_LANGUAGE) -> dict[str, list[Any]]:
    return pytesseract.image_to_data(prepare(image), lang=language, config=options(), output_type=pytesseract.Output.DICT)


def scan_lines(path: pathlib.Path, pages: list[int], language: str = DEFAULT_LANGUAGE) -> list[Line]:
    document = pypdfium2.PdfDocument(str(path))
    try:
        found: list[Line] = []
        for number in pages:
            image = render(document[number - 1])
            data = recognise(image, language)
            found.extend(tesseract_lines({"number": number, "width": image.width, "height": image.height, "data": data}))
        return found
    finally:
        document.close()
