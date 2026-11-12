import argparse
import json
import pathlib
import sys
from typing import Any

import pypdfium2

from core.detectors.scan import detect_image_only
from providers.local import tesseract

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SAMPLES = ROOT / "eval" / "samples" / "pdfs"
FIXTURES = ROOT / "eval" / "fixtures" / "tesseract"


def record(path: pathlib.Path, language: str, version: str) -> dict[str, Any] | None:
    numbers = sorted(finding.page for finding in detect_image_only(path) if finding.page is not None)
    if not numbers:
        return None
    document = pypdfium2.PdfDocument(str(path))
    try:
        pages = []
        for number in numbers:
            image = tesseract.render(document[number - 1])
            pages.append({"number": number, "width": image.width, "height": image.height, "data": tesseract.recognise(image, language)})
    finally:
        document.close()
    return {"engine": "tesseract", "version": version, "language": language, "dpi": tesseract.DPI, "pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Tesseract output for the scanned pages of the samples")
    parser.add_argument("--sample", action="append", help="sample id such as 05; repeat for more; default all")
    parser.add_argument("--language", default=tesseract.DEFAULT_LANGUAGE)
    parser.add_argument("--refresh", action="store_true", help="run again even when a fixture exists")
    args = parser.parse_args()

    try:
        version = tesseract.configure()
    except tesseract.ToolMissing as error:
        print(error)
        return 2
    wrote = 0
    for path in sorted(SAMPLES.glob("*.pdf")):
        sample = path.name[:2]
        target = FIXTURES / f"{sample}.json"
        if (args.sample and sample not in args.sample) or (target.is_file() and not args.refresh):
            continue
        recorded = record(path, args.language, version)
        if recorded is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(recorded, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        wrote += 1
        print(f"{sample}: {len(recorded['pages'])} pages recorded with tesseract {version}")
    if not wrote:
        print("Nothing recorded: every scanned sample already has a fixture. Use --refresh to run again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
