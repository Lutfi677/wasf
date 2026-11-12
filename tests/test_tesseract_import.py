from test_azure_imports import ROOT, imported_modules, repository_python_files

PROVIDER = "providers/local/tesseract.py"


def imports_pytesseract(source: str) -> bool:
    return any(name == "pytesseract" or name.startswith("pytesseract.") for name in imported_modules(source))


def test_detects_pytesseract_imports():
    assert imports_pytesseract("import pytesseract")
    assert imports_pytesseract("from pytesseract import Output")
    assert not imports_pytesseract("import pytesseractx")
    assert not imports_pytesseract("from providers.local import tesseract")


def test_only_the_local_provider_imports_pytesseract():
    importers = {
        path.relative_to(ROOT).as_posix()
        for path in repository_python_files()
        if imports_pytesseract(path.read_text(encoding="utf-8-sig"))
    }
    assert importers == {PROVIDER}
