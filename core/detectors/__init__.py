from pathlib import Path

from core.detectors.contrast import detect_contrast
from core.detectors.links import detect_links
from core.detectors.metadata import detect_metadata
from core.detectors.scan import detect_image_only
from core.findings import Finding

RULE_IDS = ("NO_TAGS", "NO_TITLE", "BAD_TITLE", "NO_LANG", "LOW_CONTRAST", "VAGUE_LINK", "RAW_URL", "IMAGE_ONLY")
DETECTORS = (detect_metadata, detect_contrast, detect_links, detect_image_only)


def detect(path: Path) -> list[Finding]:
    found = [finding for detector in DETECTORS for finding in detector(Path(path))]
    return sorted(found, key=lambda finding: (finding.page or 0, RULE_IDS.index(finding.defect)))
