import ast
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
AZURE_PACKAGES = {"azure", "openai"}
PYTHON_FOLDERS = (ROOT / "core",)
CSHARP_FOLDER = ROOT / "review"
GENERATED = {"bin", "obj"}
AZURE_REFERENCE = re.compile(r"<PackageReference\s+Include\s*=\s*\"Azure\.", re.IGNORECASE)
AZURE_USING = re.compile(r"^\s*(global\s+)?using\s+(static\s+)?Azure\s*[.;]", re.MULTILINE)
CONTENT_UNDERSTANDING = "azure.ai.contentunderstanding"
PROVIDER = "providers/azure/cu.py"
HARNESS = ROOT / "eval" / "harness"
SKIPPED = {".venv", ".git", ".claude", "node_modules", "bin", "obj", "__pycache__", "build"}
EXEMPT_SETUP = ("eval", "azure_setup")


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


def imported_modules(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def imports_content_understanding(source: str) -> bool:
    return any(name == CONTENT_UNDERSTANDING or name.startswith(CONTENT_UNDERSTANDING + ".") for name in imported_modules(source))


def repository_python_files():
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = [name for name in subfolders if name not in SKIPPED]
        here = pathlib.Path(folder)
        if here.relative_to(ROOT).parts[:2] == EXEMPT_SETUP:
            continue
        yield from (here / name for name in files if name.endswith(".py"))


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


def test_detects_content_understanding_imports():
    assert imports_content_understanding("from azure.ai.contentunderstanding import ContentUnderstandingClient")
    assert imports_content_understanding("import azure.ai.contentunderstanding.models")
    assert not imports_content_understanding("from azure.identity import DefaultAzureCredential")
    assert not imports_content_understanding("import azure.ai.contentunderstandingx")


def test_only_the_provider_imports_content_understanding():
    importers = {
        path.relative_to(ROOT).as_posix()
        for path in repository_python_files()
        if imports_content_understanding(path.read_text(encoding="utf-8-sig"))
    }
    assert importers == {PROVIDER}


def test_local_and_recorded_providers_do_not_import_azure_packages():
    folders = (ROOT / "providers" / "local", ROOT / "providers" / "recorded")
    offenders = {path.name: azure_imports(path.read_text(encoding="utf-8-sig")) for folder in folders for path in folder.rglob("*.py")}
    assert offenders
    assert {name: found for name, found in offenders.items() if found} == {}


def test_the_service_provider_class_does_not_import_azure_packages():
    source = (ROOT / "providers" / "azure" / "cu_provider.py").read_text(encoding="utf-8-sig")
    assert azure_imports(source) == set()


def test_harness_does_not_import_azure_packages():
    offenders = {path.name: azure_imports(path.read_text(encoding="utf-8-sig")) for path in HARNESS.rglob("*.py")}
    assert {name: found for name, found in offenders.items() if found} == {}


def test_review_does_not_reference_azure_packages():
    offenders = [str(path.relative_to(ROOT)) for path in csharp_files() if azure_references(path.read_text(encoding="utf-8-sig"))]
    assert offenders == []
