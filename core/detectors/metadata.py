import re
from pathlib import Path

import pikepdf

from core.detectors.text import quoted
from core.findings import Finding

BAD_TITLE_PATTERNS = (
    re.compile(r"^microsoft (word|excel|powerpoint) - ", re.IGNORECASE),
    re.compile(r"\.(docx?|xlsx?|pptx?|indd|pdf|odt|rtf|txt|tex|ai|psd)$", re.IGNORECASE),
    re.compile(r"^(untitled|document|presentation|book|slide)\s*\d*$", re.IGNORECASE),
)


def is_bad_title(title: str) -> bool:
    cleaned = title.strip()
    return any(pattern.search(cleaned) for pattern in BAD_TITLE_PATTERNS)


def document_title(pdf: pikepdf.Pdf) -> str | None:
    info = pdf.docinfo.get("/Title")
    if info is not None and str(info).strip():
        return str(info)
    title = pdf.open_metadata().get("dc:title")
    if title and str(title).strip():
        return str(title)
    return None


def detect_metadata(path: Path) -> list[Finding]:
    found = []
    with pikepdf.open(path) as pdf:
        root = pdf.Root
        mark_info = root.get("/MarkInfo")
        marked = mark_info is not None and bool(mark_info.get("/Marked", False))
        if not (marked and "/StructTreeRoot" in root):
            found.append(Finding(defect="NO_TAGS", evidence="The file is not marked as tagged, or it has no structure tree"))
        title = document_title(pdf)
        if title is None:
            found.append(Finding(defect="NO_TITLE", evidence="No title in the Info dictionary or in the XMP metadata"))
        elif is_bad_title(title):
            found.append(Finding(defect="BAD_TITLE", evidence=f"The title is a file name or a default: {quoted(title)}"))
        language = root.get("/Lang")
        if language is None or not str(language).strip():
            found.append(Finding(defect="NO_LANG", evidence="No document language (/Lang) in the catalogue"))
    return found
