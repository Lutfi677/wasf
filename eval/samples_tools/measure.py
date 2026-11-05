import ctypes
import json
import pathlib
import re

import fingerprint
import numpy as np
import pikepdf
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

SCALE = 4
RULE_IDS = ("NO_TAGS", "NO_TITLE", "BAD_TITLE", "NO_LANG", "LOW_CONTRAST", "VAGUE_LINK", "RAW_URL", "IMAGE_ONLY")
METADATA_IDS = ("NO_TAGS", "NO_TITLE", "BAD_TITLE", "NO_LANG")
PLAN_COUNTS = {
    "NO_TAGS": 8,
    "NO_TITLE": 4,
    "BAD_TITLE": 4,
    "NO_LANG": 8,
    "LOW_CONTRAST": 3,
    "VAGUE_LINK": 1,
    "RAW_URL": 2,
    "IMAGE_ONLY": 1,
}
VAGUE_LINK_TEXTS = {"click here", "here", "read more", "more", "this link", "link", "click", "learn more"}
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)]", re.IGNORECASE)
BAD_TITLE_PATTERNS = (
    re.compile(r"^microsoft (word|excel|powerpoint) - ", re.IGNORECASE),
    re.compile(r"\.(docx?|xlsx?|pptx?|indd|pdf|odt|rtf|txt|tex|ai|psd)$", re.IGNORECASE),
    re.compile(r"^(untitled|document|presentation|book|slide)\s*\d*$", re.IGNORECASE),
)
LARGE_TEXT_POINTS = 18
IMAGE_ONLY_COVERAGE = 0.8


def default_root():
    return pathlib.Path(__file__).resolve().parents[2] / "eval" / "samples"


def load_manifest(root):
    return json.loads((pathlib.Path(root) / "answer_key" / "manifest.json").read_text(encoding="utf-8"))


def relative_luminance(rgb):
    channels = np.array(rgb, dtype=float) / 255.0
    linear = np.where(channels <= 0.03928, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2])


def contrast_ratio(first, second):
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def is_bad_title(title):
    cleaned = title.strip()
    return any(pattern.search(cleaned) for pattern in BAD_TITLE_PATTERNS)


def is_vague_link_text(text):
    cleaned = re.sub(r"[^\w ]", "", fingerprint.normalise(text)).strip().lower()
    return cleaned in VAGUE_LINK_TEXTS


def metadata_findings(pdf):
    found = set()
    mark_info = pdf.Root.get("/MarkInfo")
    marked = mark_info is not None and bool(mark_info.get("/Marked", False))
    if not (marked and "/StructTreeRoot" in pdf.Root):
        found.add("NO_TAGS")
    title = fingerprint.document_title(pdf)
    if title is None:
        found.add("NO_TITLE")
    elif is_bad_title(title):
        found.add("BAD_TITLE")
    language = pdf.Root.get("/Lang")
    if language is None or not str(language).strip():
        found.add("NO_LANG")
    return found


def render_rgb(page):
    return page.render(scale=SCALE, rev_byteorder=True).to_numpy()


def crop_pixels(bitmap, page_height, bounds):
    left, bottom, right, top = bounds
    x0, x1 = max(int(left * SCALE), 0), min(int(right * SCALE), bitmap.shape[1])
    y0, y1 = max(int((page_height - top) * SCALE), 0), min(int((page_height - bottom) * SCALE), bitmap.shape[0])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return bitmap[y0:y1, x0:x1, :3].reshape(-1, 3)


def dominant_colour(pixels):
    quantised = (pixels // 8).astype(np.int32)
    keys = quantised[:, 0] * 1024 + quantised[:, 1] * 32 + quantised[:, 2]
    values, counts = np.unique(keys, return_counts=True)
    return pixels[keys == values[counts.argmax()]].mean(axis=0)


def text_objects(page):
    objects = []
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_TEXT], max_depth=15):
        red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
        if not pdfium_c.FPDFPageObj_GetFillColor(obj.raw, red, green, blue, alpha):
            continue
        objects.append(
            {
                "bounds": obj.get_bounds(),
                "fill": (red.value, green.value, blue.value),
                "size": obj.get_font_size(),
                "alpha": alpha.value,
            }
        )
    return objects


def text_contrasts(path):
    results = []
    doc = pdfium.PdfDocument(str(path))
    for index in range(len(doc)):
        page = doc[index]
        height = page.get_size()[1]
        bitmap = render_rgb(page)
        for item in text_objects(page):
            bounds = item["bounds"]
            if item["alpha"] == 0 or bounds[3] - bounds[1] < 2:
                continue
            pixels = crop_pixels(bitmap, height, bounds)
            if pixels is None:
                continue
            distance = np.abs(pixels.astype(float) - np.array(item["fill"], dtype=float)).sum(axis=1)
            rest = pixels[distance > 24]
            if len(rest) < 20:
                continue
            ratio = contrast_ratio(item["fill"], dominant_colour(rest))
            threshold = 3.0 if item["size"] >= LARGE_TEXT_POINTS else 4.5
            results.append({"page": index + 1, "ratio": round(ratio, 2), "threshold": threshold})
        page.close()
    doc.close()
    return results


def image_objects(page):
    return list(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=15))


def image_only_pages(path):
    pages = []
    doc = pdfium.PdfDocument(str(path))
    for index in range(len(doc)):
        page = doc[index]
        width, height = page.get_size()
        textpage = page.get_textpage()
        characters = len(textpage.get_text_range().strip())
        textpage.close()
        if characters == 0:
            coverage = 0.0
            for obj in image_objects(page):
                left, bottom, right, top = obj.get_bounds()
                coverage = max(coverage, (right - left) * (top - bottom) / (width * height))
            if coverage >= IMAGE_ONLY_COVERAGE:
                pages.append(index + 1)
        page.close()
    doc.close()
    return pages


def link_rectangles(path):
    pages = []
    with pikepdf.open(path) as pdf:
        for page in pdf.pages:
            rectangles = []
            for annotation in page.obj.get("/Annots", []):
                if annotation.get("/Subtype") == "/Link" and "/Rect" in annotation:
                    left, bottom, right, top = (float(value) for value in annotation["/Rect"])
                    rectangles.append((min(left, right), min(bottom, top), max(left, right), max(bottom, top)))
            pages.append(rectangles)
    return pages


def link_findings(path):
    found = set()
    rectangles = link_rectangles(path)
    doc = pdfium.PdfDocument(str(path))
    for index in range(len(doc)):
        page = doc[index]
        textpage = page.get_textpage()
        for left, bottom, right, top in rectangles[index]:
            if is_vague_link_text(textpage.get_text_bounded(left, bottom, right, top)):
                found.add("VAGUE_LINK")
        text = textpage.get_text_range()
        for match in URL_PATTERN.finditer(text):
            boxes = [textpage.get_charbox(position) for position in range(match.start(), match.end())]
            boxes = [box for box in boxes if box[2] > box[0] and box[3] > box[1]]
            if not boxes:
                continue
            centre_x = (min(box[0] for box in boxes) + max(box[2] for box in boxes)) / 2
            centre_y = (min(box[1] for box in boxes) + max(box[3] for box in boxes)) / 2
            covered = any(left <= centre_x <= right and bottom <= centre_y <= top for left, bottom, right, top in rectangles[index])
            if not covered:
                found.add("RAW_URL")
        textpage.close()
        page.close()
    doc.close()
    return found


def image_colour_ratios(path, page_number, minimum_pixels=1000, limit=15):
    ratios = []
    doc = pdfium.PdfDocument(str(path))
    page = doc[page_number - 1]
    height = page.get_size()[1]
    bitmap = render_rgb(page)
    for obj in image_objects(page):
        pixels = crop_pixels(bitmap, height, obj.get_bounds())
        if pixels is None:
            continue
        keys = (pixels[:, 0].astype(np.int64) << 16) | (pixels[:, 1].astype(np.int64) << 8) | pixels[:, 2]
        values, counts = np.unique(keys, return_counts=True)
        order = counts.argsort()[::-1][: limit + 1]

        def colour(value):
            return ((int(value) >> 16) & 255, (int(value) >> 8) & 255, int(value) & 255)

        background = colour(values[order[0]])
        for position in order[1:]:
            if counts[position] >= minimum_pixels:
                ratios.append(round(contrast_ratio(colour(values[position]), background), 2))
    page.close()
    doc.close()
    return ratios


def findings(path):
    found = set()
    with pikepdf.open(path) as pdf:
        found |= metadata_findings(pdf)
    if any(item["ratio"] < item["threshold"] for item in text_contrasts(path)):
        found.add("LOW_CONTRAST")
    if image_only_pages(path):
        found.add("IMAGE_ONLY")
    found |= link_findings(path)
    return found
