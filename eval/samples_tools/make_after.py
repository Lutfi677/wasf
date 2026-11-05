import argparse
import pathlib
import re
import sys

import measure
import pikepdf

LANGUAGE_PATTERN = re.compile(r"^(?:bilingual\s+)?([a-z]{2,3}(?:-[A-Za-z]{2,4})?)\b")
STATEMENT = (
    "These copies fix four metadata types only (NO_TAGS, NO_TITLE, BAD_TITLE, NO_LANG). "
    "They are not accessible documents: the structure tree is empty and nothing else was changed."
)


def language_code(expected):
    match = LANGUAGE_PATTERN.match(expected.strip())
    if match is None:
        raise ValueError(f"no language code in language_expected: {expected!r}")
    return match.group(1)


def write_after(source, target, title, language):
    with pikepdf.open(source) as pdf:
        pdf.docinfo["/Title"] = title
        pdf.Root.Lang = language
        pdf.Root.MarkInfo = pikepdf.Dictionary(Marked=True)
        pdf.Root.StructTreeRoot = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot, K=pikepdf.Array()))
        pdf.save(target, static_id=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write pdfs_after: the originals with the four metadata types fixed")
    parser.add_argument("--samples", default=str(measure.default_root()))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.samples)
    manifest = measure.load_manifest(root)
    folder = root / "pdfs_after"
    folder.mkdir(parents=True, exist_ok=True)
    for entry in manifest["documents"]:
        name = pathlib.PurePosixPath(entry["file"]).name
        language = language_code(entry["language_expected"])
        write_after(root / entry["file"], folder / name, entry["title_expected"], language)
        print(f"{name}: title and /Lang {language} set, MarkInfo Marked true, empty StructTreeRoot")
    print(STATEMENT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
