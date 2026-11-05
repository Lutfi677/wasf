import argparse
import pathlib
import sys

import fingerprint
import measure
import pikepdf

CONTRAST_TOLERANCE = 0.15
IMAGE_TOLERANCE = 0.05
LISTED_IMAGES = 13
DOCUMENTS = 8


def measured_properties(path):
    with pikepdf.open(path) as pdf:
        info = {str(key): str(value) for key, value in pdf.docinfo.items()}
        image_count = 0
        for page in pdf.pages:
            resources = page.obj.get("/Resources")
            xobjects = resources.get("/XObject") if resources is not None else None
            if xobjects is not None:
                image_count += sum(1 for _, obj in xobjects.items() if obj.get("/Subtype") == "/Image")
        properties = {
            "pages": len(pdf.pages),
            "tagged": "/StructTreeRoot" in pdf.Root or "/MarkInfo" in pdf.Root,
            "declares_language": "/Lang" in pdf.Root,
            "title": info.get("/Title"),
            "image_objects": image_count,
        }
    counts = [len(text.replace("\r\n", "\n").strip()) for text in fingerprint.raw_page_texts(path.read_bytes())]
    properties["text_chars_per_page"] = counts
    return properties


def check_properties(name, entry, path):
    failures = 0
    expected = entry["verified_properties"]
    measured = measured_properties(path)
    for key, value in expected.items():
        if measured.get(key) != value:
            print(f"FAIL {name}: verified_properties.{key} is {value!r} in the manifest but {measured.get(key)!r} in the file")
            failures += 1
    return failures


def check_contrast(name, entry, path):
    failures = 0
    entries = entry.get("contrast_checks", [])
    if not entries:
        return 0
    measured = sorted({item["ratio"] for item in measure.text_contrasts(path)})
    for number, check in enumerate(entries):
        listed = check["ratio"]
        nearest = min(measured, key=lambda value: abs(value - listed)) if measured else None
        if nearest is not None and abs(nearest - listed) <= CONTRAST_TOLERANCE:
            continue
        element = check["element"].lower()
        matched = False
        for image in entry.get("images", []):
            if image["id"].replace("-", " ") in element:
                ratios = measure.image_colour_ratios(path, image["page"])
                matched = any(abs(value - listed) <= IMAGE_TOLERANCE for value in ratios)
        if not matched:
            print(f"FAIL {name}: contrast_checks[{number}] ratio {listed} has no measurement within tolerance (nearest {nearest})")
            failures += 1
    return failures


def check_manifest(root, manifest):
    failures = 0
    documents = manifest.get("documents", [])
    catalogue = manifest.get("defect_catalogue", {})
    if len(documents) != DOCUMENTS:
        print(f"FAIL manifest lists {len(documents)} documents, expected {DOCUMENTS}")
        failures += 1
    totals = {}
    listed_images = 0
    for entry in documents:
        name = pathlib.PurePosixPath(entry["file"]).name
        path = root / entry["file"]
        for item in entry["seeded_defects"]:
            totals[item["id"]] = totals.get(item["id"], 0) + 1
            if item["id"] not in catalogue:
                print(f"FAIL {name}: seeded defect {item['id']} is not in the defect catalogue")
                failures += 1
        listed_images += len(entry.get("images", []))
        if not path.is_file():
            print(f"FAIL {name}: file is missing")
            failures += 1
            continue
        failures += check_properties(name, entry, path)
        failures += check_contrast(name, entry, path)
    for defect, expected in measure.PLAN_COUNTS.items():
        if totals.get(defect, 0) != expected:
            print(f"FAIL defect count for {defect} is {totals.get(defect, 0)}, expected {expected}")
            failures += 1
    if listed_images != LISTED_IMAGES:
        print(f"FAIL manifest lists {listed_images} images, expected {LISTED_IMAGES}")
        failures += 1
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the sample manifest against the sample PDFs")
    parser.add_argument("--samples", default=str(measure.default_root()))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.samples)
    failures = check_manifest(root, measure.load_manifest(root))
    print(f"check_manifest: {'failed, ' + str(failures) + ' failure(s)' if failures else 'ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
