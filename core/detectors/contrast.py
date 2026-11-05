import ctypes
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from core.findings import Finding

SCALE = 4
LARGE_TEXT_POINTS = 18
NORMAL_MINIMUM = 4.5
LARGE_MINIMUM = 3.0
FILL_DISTANCE = 24
BACKGROUND_PIXELS = 20


def relative_luminance(rgb) -> float:
    channels = np.array(rgb, dtype=float) / 255.0
    linear = np.where(channels <= 0.03928, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2])


def contrast_ratio(first, second) -> float:
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


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


def text_runs(page):
    runs = []
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_TEXT], max_depth=15):
        red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
        if not pdfium_c.FPDFPageObj_GetFillColor(obj.raw, red, green, blue, alpha):
            continue
        runs.append(
            {
                "bounds": obj.get_bounds(),
                "fill": (red.value, green.value, blue.value),
                "size": obj.get_font_size(),
                "alpha": alpha.value,
            }
        )
    return runs


def page_contrasts(page) -> list[tuple[float, float]]:
    results = []
    height = page.get_size()[1]
    bitmap = render_rgb(page)
    for run in text_runs(page):
        bounds = run["bounds"]
        if run["alpha"] == 0 or bounds[3] - bounds[1] < 2:
            continue
        pixels = crop_pixels(bitmap, height, bounds)
        if pixels is None:
            continue
        distance = np.abs(pixels.astype(float) - np.array(run["fill"], dtype=float)).sum(axis=1)
        rest = pixels[distance > FILL_DISTANCE]
        if len(rest) < BACKGROUND_PIXELS:
            continue
        ratio = round(contrast_ratio(run["fill"], dominant_colour(rest)), 2)
        minimum = LARGE_MINIMUM if run["size"] >= LARGE_TEXT_POINTS else NORMAL_MINIMUM
        results.append((ratio, minimum))
    return results


def runs_below(count: int) -> str:
    return "1 text run is" if count == 1 else f"{count} text runs are"


def detect_contrast(path: Path) -> list[Finding]:
    found = []
    doc = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(doc)):
            page = doc[index]
            low = [(ratio, minimum) for ratio, minimum in page_contrasts(page) if ratio < minimum]
            page.close()
            if low:
                ratio, minimum = min(low)
                lowest = f"the lowest is {ratio:.2f}:1 where {minimum:g}:1 is needed"
                evidence = f"{runs_below(len(low))} below the minimum on this page; {lowest}"
                found.append(Finding(defect="LOW_CONTRAST", page=index + 1, evidence=evidence))
    finally:
        doc.close()
    return found
