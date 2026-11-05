import argparse
import pathlib
import sys

import fingerprint
import measure


def check_originals(root, manifest):
    failures = 0
    seeded_total = 0
    seeded_found = 0
    unseeded = []
    for entry in manifest["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        path = root / entry["file"]
        if not path.is_file():
            print(f"FAIL {name}: file is missing")
            failures += 1
            continue
        expected = {item["id"] for item in entry["seeded_defects"] if item["id"] in measure.RULE_IDS}
        found = measure.findings(path)
        seeded_total += len(expected)
        for defect in sorted(expected):
            if defect in found:
                seeded_found += 1
            else:
                print(f"FAIL {name}: {defect} is seeded but was not found")
                failures += 1
        for defect in sorted(found - expected):
            if defect in measure.METADATA_IDS:
                print(f"FAIL {name}: {defect} was found but is not seeded")
                failures += 1
            else:
                unseeded.append((name, defect))
    print(f"originals: {seeded_found} of {seeded_total} seeded rule-checkable defects found")
    for name, defect in unseeded:
        print(f"note {name}: {defect} found but not seeded in the manifest")
    return failures


def check_after(root, manifest):
    folder = root / "pdfs_after"
    if not folder.is_dir():
        print("pdfs_after: not present, skipped")
        return 0
    failures = 0
    checked = 0
    for entry in manifest["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        path = folder / name
        if not path.is_file():
            print(f"FAIL pdfs_after/{name}: file is missing")
            failures += 1
            continue
        checked += 1
        for defect in sorted(measure.findings(path) & set(measure.METADATA_IDS)):
            print(f"FAIL pdfs_after/{name}: {defect} is still found")
            failures += 1
        before = fingerprint.fingerprint_one((root / entry["file"]).read_bytes())
        after = fingerprint.fingerprint_one(path.read_bytes())
        for field in ("pages", "text_tokens_sha256", "images"):
            if before[field] != after[field]:
                print(f"FAIL pdfs_after/{name}: {field} differs from the original")
                failures += 1
    print(f"pdfs_after: {checked} files checked for the four metadata types")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rule measurements on the sample PDFs")
    parser.add_argument("--samples", default=str(measure.default_root()))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.samples)
    manifest = measure.load_manifest(root)
    failures = check_originals(root, manifest) + check_after(root, manifest)
    print(f"check_pdf: {'failed, ' + str(failures) + ' failure(s)' if failures else 'ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
