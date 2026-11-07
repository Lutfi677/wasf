import os
import pathlib
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pdf_builder import build, line

from core.api import app, get_store
from core.findings import State, StoredFinding
from core.output import words
from core.output.report import render
from core.store import Document, Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE_01 = ROOT / "eval" / "samples" / "pdfs" / "01_county_budget_summary.pdf"
WRITTEN = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
MARKER = "MARKER-not-for-the-report"
BANNED = re.compile(r"\b(compliant|conformant|conformance|certified|accessible|verified|meets)\b", re.IGNORECASE)


def finding(number, state, page=None, fix=None):
    return StoredFinding(
        id=number, document_id=1, defect=f"RULE_{number}", page=page, evidence=f"{MARKER} {number}", state=state, proposed_fix=fix
    )


FINDINGS = [
    finding(1, State.approved, page=1),
    finding(2, State.edited, fix=f"{MARKER} fix"),
    finding(3, State.proposed, page=2),
    finding(4, State.escalated),
    finding(5, State.rejected, page=3),
]
DOCUMENT = Document(id=1, pages=3, findings=len(FINDINGS), uploaded_at=WRITTEN)


def section(report, heading):
    return report.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def listed(text):
    return {int(number) for number in re.findall(r"^\| (\d+) \|", text, flags=re.MULTILINE)}


@pytest.fixture
def report():
    return render(DOCUMENT, FINDINGS, WRITTEN)


def test_each_state_lands_in_its_section(report):
    assert listed(section(report, words.APPROVED)) == {1, 2}
    assert listed(section(report, words.OPEN)) == {3, 4}
    assert listed(section(report, words.REJECTED)) == {5}


def test_counts_match_the_sections(report):
    assert "| Approved | 2 |" in report
    assert "| Open | 2 |" in report
    assert "| Rejected | 1 |" in report


def test_the_report_has_its_title_and_ends_with_the_fixed_paragraph(report):
    assert report.startswith(f"# {words.TITLE}\n")
    assert section(report, words.NOT_CLAIMED).strip() == words.DISCLAIMER
    assert report.rstrip().endswith(words.DISCLAIMER)


def test_the_report_holds_no_evidence_and_no_fix_text(report):
    assert MARKER not in report


def test_no_conformance_word_in_the_report_or_in_the_words(report):
    assert not BANNED.search(report)
    assert not [text for text in words.ALL if BANNED.search(text)]


def test_an_empty_section_says_none():
    report = render(Document(id=2, pages=1, findings=1, uploaded_at=WRITTEN), [finding(1, State.proposed)], WRITTEN)
    assert section(report, words.APPROVED).strip() == words.NONE
    assert section(report, words.REJECTED).strip() == words.NONE
    assert "Document 2, 1 page, 1 finding." in report


def test_the_time_written_is_in_utc():
    later = WRITTEN.astimezone(timezone(timedelta(hours=3)))
    assert "Written 2026-11-07 12:00 UTC." in render(DOCUMENT, FINDINGS, later)


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "store" / "wasf.sqlite3", tmp_path / "store" / "documents")
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    store.close()


def upload(client, path):
    with path.open("rb") as handle:
        response = client.post("/documents", files={"file": ("upload.pdf", handle, "application/pdf")})
    assert response.status_code == 201
    return response.json()


def test_the_route_answers_markdown(client, tmp_path):
    path = build(tmp_path, line("click here", grey=150), name="upload.pdf", title="Document1", links=[(68, 694, 140, 714)])
    document = upload(client, path)
    response = client.get(f"/documents/{document['id']}/report")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.rstrip().endswith(words.DISCLAIMER)
    assert listed(section(response.text, words.OPEN)) == {item["id"] for item in client.get(f"/documents/{document['id']}/findings").json()}


def test_the_route_answers_404_for_an_unknown_document(client):
    assert client.get("/documents/999/report").status_code == 404


def test_the_report_for_sample_01_lists_every_approved_and_every_open_finding(client):
    if not SAMPLE_01.is_file():
        if os.environ.get("CI"):
            pytest.fail("eval/samples is missing in CI")
        pytest.skip("eval/samples has not been generated: run make_samples.py in eval/samples_tools")
    document = upload(client, SAMPLE_01)
    findings = client.get(f"/documents/{document['id']}/findings").json()
    approved, rejected = findings[0]["id"], findings[1]["id"]
    assert client.post(f"/findings/{approved}/decision", json={"state": "approved"}).status_code == 200
    assert client.post(f"/findings/{rejected}/decision", json={"state": "rejected"}).status_code == 200
    report = client.get(f"/documents/{document['id']}/report").text
    assert listed(section(report, words.APPROVED)) == {approved}
    assert listed(section(report, words.OPEN)) == {item["id"] for item in findings[2:]}
    assert listed(section(report, words.REJECTED)) == {rejected}
    assert not [item["evidence"] for item in findings if item["evidence"] in report]
