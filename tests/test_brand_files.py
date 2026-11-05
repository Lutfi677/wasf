import json
import pathlib
import re
import struct
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_BRAND = ROOT / "docs" / "brand"
WWWROOT = ROOT / "review" / "wwwroot"
BRAND = WWWROOT / "brand"

DOCS_FILES = ["banner-light.svg", "banner-dark.svg", "social-preview.png"]
LOGO_FILES = [
    "favicon.ico",
    "favicon.svg",
    "lockup-horizontal-ltr-mono.svg",
    "lockup-horizontal-ltr-reverse.svg",
    "lockup-horizontal-ltr.svg",
    "lockup-horizontal-rtl-mono.svg",
    "lockup-horizontal-rtl-reverse.svg",
    "lockup-horizontal-rtl.svg",
    "lockup-stacked-mono.svg",
    "lockup-stacked-reverse.svg",
    "lockup-stacked.svg",
    "mark-mono.svg",
    "mark-reverse.svg",
    "mark.svg",
    "wordmark-arabic-mono.svg",
    "wordmark-arabic-reverse.svg",
    "wordmark-arabic.svg",
    "wordmark-latin-mono.svg",
    "wordmark-latin-reverse.svg",
    "wordmark-latin.svg",
]
FONT_FILES = [
    "fonts.css",
    "ibm-plex-mono-latin-400-normal.woff2",
    "ibm-plex-sans-arabic-arabic-400-normal.woff2",
    "ibm-plex-sans-arabic-arabic-600-normal.woff2",
    "ibm-plex-sans-latin-400-normal.woff2",
    "ibm-plex-sans-latin-600-normal.woff2",
    "LICENSE-ibm-plex-mono.txt",
    "LICENSE-ibm-plex-sans-arabic.txt",
    "LICENSE-ibm-plex-sans.txt",
]
FONT_LICENCES = {
    "ibm-plex-sans-arabic": "LICENSE-ibm-plex-sans-arabic.txt",
    "ibm-plex-sans-latin": "LICENSE-ibm-plex-sans.txt",
    "ibm-plex-mono": "LICENSE-ibm-plex-mono.txt",
}
EXPECTED = (
    [DOCS_BRAND / name for name in DOCS_FILES]
    + [BRAND / "logo" / name for name in LOGO_FILES]
    + [BRAND / "fonts" / name for name in FONT_FILES]
    + [BRAND / "tokens" / "tokens.css", BRAND / "tokens" / "tokens.json", WWWROOT / "css" / "components.css"]
)
SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", "build", "node_modules", ".ruff_cache", ".pytest_cache"}
SKIPPED_PREFIXES = ("eval/samples/",)
OLD_NAME = b"doc" + b"able"


def svg_files():
    return sorted(DOCS_BRAND.glob("*.svg")) + sorted((BRAND / "logo").glob("*.svg"))


@pytest.mark.parametrize("path", EXPECTED, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_brand_file_exists(path):
    assert path.is_file()


@pytest.mark.parametrize("path", svg_files(), ids=lambda path: path.relative_to(ROOT).as_posix())
def test_svg_files_parse(path):
    root = ET.parse(path).getroot()
    assert root.tag.endswith("}svg") or root.tag == "svg"


@pytest.mark.parametrize("name", ["banner-light.svg", "banner-dark.svg"])
def test_banners_have_the_banner_view_box(name):
    root = ET.parse(DOCS_BRAND / name).getroot()
    assert root.get("viewBox") == "0 0 1280 320"


def test_social_preview_is_1280_by_640():
    header = (DOCS_BRAND / "social-preview.png").read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", header[16:24]) == (1280, 640)


def test_font_css_names_only_existing_files():
    folder = BRAND / "fonts"
    references = re.findall(r'url\("\./([^"]+)"\)', (folder / "fonts.css").read_text(encoding="utf-8"))
    assert references
    for reference in references:
        assert (folder / reference).is_file(), reference


def test_every_font_file_has_its_licence_file():
    folder = BRAND / "fonts"
    for font in folder.glob("*.woff2"):
        licence = next(file for prefix, file in FONT_LICENCES.items() if font.name.startswith(prefix))
        assert (folder / licence).is_file(), font.name


def test_tokens_are_readable():
    tokens = json.loads((BRAND / "tokens" / "tokens.json").read_text(encoding="utf-8"))
    assert "color" in tokens
    css = (BRAND / "tokens" / "tokens.css").read_text(encoding="utf-8")
    assert ":root" in css
    assert len(re.findall(r"--[a-z0-9-]+\s*:", css)) >= 10


def test_readme_banner_points_at_existing_files():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count("<picture>") == 1
    paths = re.findall(r'(?:srcset|src)="([^"]+)"', readme)
    assert len(paths) == 2
    for path in paths:
        assert (ROOT / path).is_file(), path
    alt = re.search(r'alt="([^"]*)"', readme)
    assert alt is not None and alt.group(1).strip()


def test_old_name_appears_in_no_repository_file():
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if SKIPPED_DIRECTORIES & set(relative.parts) or any(part.endswith(".egg-info") for part in relative.parts):
            continue
        if relative.as_posix().startswith(SKIPPED_PREFIXES):
            continue
        if OLD_NAME in path.read_bytes().lower():
            offenders.append(relative.as_posix())
    assert offenders == []
