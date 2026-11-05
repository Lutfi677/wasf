from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from core.findings import Finding

IMAGE_ONLY_COVERAGE = 0.8


def largest_image_coverage(page) -> float:
    width, height = page.get_size()
    coverage = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=15):
        left, bottom, right, top = obj.get_bounds()
        coverage = max(coverage, (right - left) * (top - bottom) / (width * height))
    return coverage


def detect_image_only(path: Path) -> list[Finding]:
    found = []
    doc = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(doc)):
            page = doc[index]
            textpage = page.get_textpage()
            characters = len(textpage.get_text_range().strip())
            textpage.close()
            if characters == 0:
                coverage = largest_image_coverage(page)
                if coverage >= IMAGE_ONLY_COVERAGE:
                    evidence = f"No extractable text, and one image covers {min(coverage, 1.0):.0%} of the page"
                    found.append(Finding(defect="IMAGE_ONLY", page=index + 1, evidence=evidence))
            page.close()
    finally:
        doc.close()
    return found
