import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
AZURE_PACKAGES = {"azure", "openai"}
PYTHON_FOLDERS = (ROOT / "core",)
CSHARP_FOLDER = ROOT / "review"
GENERATED = {"bin", "obj"}
AZURE_REFERENCE = re.compile(r"<PackageReference\s+Include\s*=\s*\"Azure\.", re.IGNORECASE)
AZURE_USING = re.compile(r"^\s*(global\s+)?using\s+(static\s+)?Azure\s*[.;]", re.MULTILINE)


def azure_imports(source: str) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] if node.level == 0 else []
        else:
            continue
        found.update(top for top in (name.split(".")[0] for name in names) if top in AZURE_PACKAGES)
    return found


def azure_references(text: str) -> bool:
    return bool(AZURE_REFERENCE.search(text) or AZURE_USING.search(text))


def csharp_files():
    for pattern in ("*.csproj", "*.cs"):
        for path in CSHARP_FOLDER.rglob(pattern):
            if not GENERATED & set(path.relative_to(CSHARP_FOLDER).parts):
                yield path


def test_detects_azure_imports():
    assert azure_imports("import azure.identity") == {"azure"}
    assert azure_imports("from azure.ai.projects import AIProjectClient") == {"azure"}


def test_detects_openai_imports():
    assert azure_imports("from openai import OpenAI") == {"openai"}


def test_ignores_other_and_relative_imports():
    assert azure_imports("import pikepdf\nfrom core.findings import Finding\nfrom .azure import client") == set()


def test_detects_azure_package_references():
    assert azure_references('<PackageReference Include="Azure.Identity" Version="1.13.0" />')
    assert not azure_references('<PackageReference Include="Microsoft.Kiota.Bundle" Version="1.17.0" />')


def test_detects_azure_using_directives():
    assert azure_references("using Azure.Identity;")
    assert azure_references("global using Azure;")
    assert not azure_references("using AzureLike.Tools;")
    assert not azure_references("using Wasf.Review.Client;")


def test_core_does_not_import_azure_packages():
    offenders = {
        str(path.relative_to(ROOT)): azure_imports(path.read_text(encoding="utf-8-sig"))
        for folder in PYTHON_FOLDERS
        for path in folder.rglob("*.py")
    }
    assert {name: found for name, found in offenders.items() if found} == {}


def test_review_does_not_reference_azure_packages():
    offenders = [str(path.relative_to(ROOT)) for path in csharp_files() if azure_references(path.read_text(encoding="utf-8-sig"))]
    assert offenders == []
