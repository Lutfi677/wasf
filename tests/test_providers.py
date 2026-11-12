import json
import pathlib

import pytest

from core.model import assemble as assembly
from core.model.provider import Provider
from providers.azure.cu_provider import ContentUnderstandingProvider
from providers.local.own import LocalProvider
from providers.recorded.recorded import SERVICE, RecordedProvider, recorded_scan_lines

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDFS = ROOT / "eval" / "samples" / "pdfs"


def file_for(tmp_path: pathlib.Path, sample: str) -> pathlib.Path:
    path = tmp_path / f"{sample}_example.pdf"
    path.write_bytes(b"%PDF-1.7")
    return path


def generated() -> list[pathlib.Path]:
    found = sorted(PDFS.glob("*.pdf"))
    if len(found) != 8:
        pytest.skip("eval/samples has not been generated")
    return found


def test_the_service_provider_reads_a_response_like_the_recorded_provider(tmp_path):
    path = file_for(tmp_path, "01")
    response = json.loads((SERVICE / "01.json").read_text(encoding="utf-8"))
    provider = ContentUnderstandingProvider(lambda data: (response, {"documentPagesStandard": 3}, 1.5))
    assert provider.read(path) == RecordedProvider().read(path)
    assert provider.calls == [{"usage": {"documentPagesStandard": 3}, "seconds": 1.5}]


def test_the_service_provider_sends_the_file_it_was_given(tmp_path):
    path = file_for(tmp_path, "01")
    response = json.loads((SERVICE / "01.json").read_text(encoding="utf-8"))
    sent: list[bytes] = []

    def analyze(data: bytes):
        sent.append(data)
        return response, {}, 0.0

    ContentUnderstandingProvider(analyze).read(path)
    assert sent == [b"%PDF-1.7"]


def test_all_three_providers_fit_the_interface():
    providers: list[Provider] = [RecordedProvider(), LocalProvider(), ContentUnderstandingProvider(lambda data: ({}, {}, 0.0))]
    assert [provider.name for provider in providers] == ["recorded", "local", "content-understanding"]


def test_the_recorded_provider_refuses_a_sample_with_no_fixture(tmp_path):
    with pytest.raises(FileNotFoundError):
        RecordedProvider().read(file_for(tmp_path, "99"))


def test_recorded_scan_lines_come_only_from_the_scanned_pages_asked_for(tmp_path):
    both = recorded_scan_lines(file_for(tmp_path, "05"), [1, 2])
    second = recorded_scan_lines(file_for(tmp_path, "05"), [2])
    assert {line["page"] for line in both} == {1, 2}
    assert {line["page"] for line in second} == {2}
    assert all(line["source"] == "tesseract" for line in both)
    assert recorded_scan_lines(file_for(tmp_path, "01"), [1]) == []


def test_the_local_provider_reads_a_digital_sample_without_calling_the_scan_reader():
    paths = generated()
    called: list[object] = []
    result = LocalProvider(lambda path, pages: called.append(pages) or []).read(paths[0])
    assert result.get("scan_pages") == []
    assert result.get("lines") == []
    assert called == []
    assert [block["reading_order"] for block in result["blocks"]] == list(range(len(result["blocks"])))


def test_the_local_provider_finds_the_scan_and_reads_it_with_the_reader():
    paths = generated()
    scan = next(path for path in paths if path.name.startswith("05"))
    result = LocalProvider(recorded_scan_lines).read(scan)
    assert result["blocks"] == []
    assert result.get("scan_pages") == [1, 2]
    assert result.get("lines")
    assert LocalProvider().read(scan).get("lines") == []


def test_every_sample_builds_a_valid_document_from_each_provider_alone_and_together():
    local = LocalProvider(recorded_scan_lines)
    recorded = RecordedProvider()
    for path in generated():
        service_result = recorded.read(path)
        local_result = local.read(path)
        for first, second in ((service_result, None), (None, local_result), (service_result, local_result)):
            document = assembly.assemble(first, second)
            assert [page.number for page in document.pages] == [page["number"] for page in (service_result["pages"])]
