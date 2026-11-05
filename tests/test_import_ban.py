import ast
import pathlib

BANNED = {"pymupdf", "fitz"}
ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANNED = (ROOT / "core", ROOT / "eval")


def banned_imports(source: str) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        found.update(top for top in (name.split(".")[0] for name in names) if top in BANNED)
    return found


def test_detects_plain_import():
    assert banned_imports("import fitz") == {"fitz"}


def test_detects_from_import():
    assert banned_imports("from pymupdf import Document") == {"pymupdf"}


def test_core_and_eval_do_not_import_pymupdf():
    offenders = {
        str(path.relative_to(ROOT)): banned_imports(path.read_text(encoding="utf-8-sig"))
        for folder in SCANNED
        for path in folder.rglob("*.py")
    }
    assert {name: found for name, found in offenders.items() if found} == {}
