import argparse
import hashlib
import io
import json
import pathlib
import sys
import unicodedata
import zipfile

import pikepdf
import pypdfium2 as pdfium


def normalise(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def raw_page_texts(data):
    doc = pdfium.PdfDocument(data)
    texts = []
    for index in range(len(doc)):
        page = doc[index]
        textpage = page.get_textpage()
        texts.append(textpage.get_text_range())
        textpage.close()
        page.close()
    doc.close()
    return texts


def page_texts(data):
    return [normalise(text) for text in raw_page_texts(data)]


def tag_state(pdf):
    marked = False
    mark_info = pdf.Root.get("/MarkInfo")
    if mark_info is not None:
        marked = bool(mark_info.get("/Marked", False))
    has_tree = "/StructTreeRoot" in pdf.Root
    if marked and has_tree:
        return "tagged"
    if marked or has_tree:
        return "partial"
    return "untagged"


def document_title(pdf):
    info = pdf.docinfo.get("/Title")
    if info is not None and str(info).strip():
        return str(info)
    title = pdf.open_metadata().get("dc:title")
    if title and str(title).strip():
        return str(title)
    return None


def image_sizes(pdf):
    pages = []
    for page in pdf.pages:
        sizes = sorted([int(image.Width), int(image.Height)] for image in page.get_images().values())
        pages.append(sizes)
    return pages


def fingerprint_one(data):
    texts = page_texts(data)
    with pikepdf.open(io.BytesIO(data)) as pdf:
        language = pdf.Root.get("/Lang")
        return {
            "pages": len(texts),
            "text_tokens_sha256": hashlib.sha256("\f".join(" ".join(sorted(text.split())) for text in texts).encode("utf-8")).hexdigest(),
            "tag_state": tag_state(pdf),
            "language": str(language) if language is not None else None,
            "title": document_title(pdf),
            "images": image_sizes(pdf),
        }


def read_pdfs(source):
    source = pathlib.Path(source)
    found = {}
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".pdf") and "/pdfs/" in "/" + name:
                    found[pathlib.PurePosixPath(name).name] = archive.read(name)
    else:
        folder = source / "pdfs" if (source / "pdfs").is_dir() else source
        for path in sorted(folder.glob("*.pdf")):
            found[path.name] = path.read_bytes()
    return found


def compute(source):
    pdfs = read_pdfs(source)
    return {name: fingerprint_one(pdfs[name]) for name in sorted(pdfs)}


def load(source):
    path = pathlib.Path(source)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return compute(path)


def differences(left, right):
    lines = []
    for name in sorted(set(left) | set(right)):
        if name not in left or name not in right:
            lines.append(f"{name}: present on one side only")
            continue
        for field in sorted(set(left[name]) | set(right[name])):
            if left[name].get(field) != right[name].get(field):
                lines.append(f"{name}: {field}: {left[name].get(field)!r} != {right[name].get(field)!r}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Content fingerprint of a set of sample PDFs")
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write")
    write.add_argument("source")
    write.add_argument("output")
    compare = commands.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    args = parser.parse_args(argv)
    if args.command == "write":
        result = compute(args.source)
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {len(result)} fingerprints to {output}")
        return 0
    lines = differences(load(args.left), load(args.right))
    for line in lines:
        print(line)
    print(f"{len(lines)} difference(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
