import logging
import secrets

import pikepdf
import pytest
from fastapi.testclient import TestClient
from pdf_builder import build, line

import core.api
from core.api import app, get_store
from core.detectors import detect
from core.store import Store


def open_store(folder):
    return Store(folder / "store" / "wasf.sqlite3", folder / "store" / "documents")


@pytest.fixture
def store(tmp_path):
    store = open_store(tmp_path)
    yield store
    store.close()


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def sample(folder, name="upload.pdf"):
    return build(folder, line("click here", grey=150), name=name, title="Document1", links=[(68, 694, 140, 714)])


def upload(client, path, name="upload.pdf"):
    with path.open("rb") as handle:
        return client.post("/documents", files={"file": (name, handle, "application/pdf")})


def upload_bytes(client, data, name="upload.pdf", kind="application/pdf"):
    return client.post("/documents", files={"file": (name, data, kind)})


def first_finding(client, document_id):
    return client.get(f"/documents/{document_id}/findings").json()[0]


def test_upload_stores_the_document_and_its_findings(client, store, tmp_path):
    path = sample(tmp_path)
    response = upload(client, path)
    assert response.status_code == 201
    body = response.json()
    assert (body["pages"], body["findings"]) == (1, len(detect(path)))
    assert (store.files / f"{body['id']}.pdf").read_bytes() == path.read_bytes()
    assert sorted(item.name for item in store.files.iterdir()) == [f"{body['id']}.pdf"]


def test_documents_are_listed_in_upload_order(client, tmp_path):
    first = upload(client, sample(tmp_path)).json()
    second = upload(client, sample(tmp_path, name="second.pdf")).json()
    listed = client.get("/documents").json()
    assert [item["id"] for item in listed] == [first["id"], second["id"]]
    assert [item["findings"] for item in listed] == [first["findings"], second["findings"]]


def test_findings_are_listed_unreviewed_in_detector_order(client, tmp_path):
    path = sample(tmp_path)
    document_id = upload(client, path).json()["id"]
    findings = client.get(f"/documents/{document_id}/findings").json()
    assert [item["defect"] for item in findings] == [finding.defect for finding in detect(path)]
    assert {item["state"] for item in findings} == {"proposed"}
    assert {item["document_id"] for item in findings} == {document_id}
    assert len({item["id"] for item in findings}) == len(findings)


def test_an_approval_survives_a_restart(tmp_path):
    first = open_store(tmp_path)
    app.dependency_overrides[get_store] = lambda: first
    try:
        with TestClient(app) as client:
            document_id = upload(client, sample(tmp_path)).json()["id"]
            finding_id = first_finding(client, document_id)["id"]
            assert client.post(f"/findings/{finding_id}/decision", json={"state": "approved"}).status_code == 200
        first.close()
        second = open_store(tmp_path)
        app.dependency_overrides[get_store] = lambda: second
        with TestClient(app) as client:
            assert first_finding(client, document_id)["state"] == "approved"
        second.close()
    finally:
        app.dependency_overrides.clear()


def test_an_edit_replaces_the_fix(client, tmp_path):
    finding_id = first_finding(client, upload(client, sample(tmp_path)).json()["id"])["id"]
    response = client.post(f"/findings/{finding_id}/decision", json={"state": "edited", "proposed_fix": "Annual fee schedule 2026"})
    assert response.status_code == 200
    assert (response.json()["state"], response.json()["proposed_fix"]) == ("edited", "Annual fee schedule 2026")


@pytest.mark.parametrize(
    "decision",
    [
        {"state": "edited"},
        {"state": "edited", "proposed_fix": "   "},
        {"state": "proposed"},
        {"state": "approved", "proposed_fix": "Annual fee schedule 2026"},
        {"state": "applied"},
    ],
)
def test_invalid_decisions_are_refused(client, tmp_path, decision):
    document_id = upload(client, sample(tmp_path)).json()["id"]
    finding_id = first_finding(client, document_id)["id"]
    assert client.post(f"/findings/{finding_id}/decision", json=decision).status_code == 422
    assert first_finding(client, document_id)["state"] == "proposed"


def test_changing_a_decision_keeps_the_history(client, store, tmp_path):
    finding_id = first_finding(client, upload(client, sample(tmp_path)).json()["id"])["id"]
    client.post(f"/findings/{finding_id}/decision", json={"state": "approved"})
    response = client.post(f"/findings/{finding_id}/decision", json={"state": "rejected"})
    assert response.json()["state"] == "rejected"
    assert [row["state"] for row in store.decisions(finding_id)] == ["approved", "rejected"]


def test_unknown_ids_are_not_found(client):
    assert client.get("/documents/999/findings").status_code == 404
    assert client.post("/findings/999/decision", json={"state": "approved"}).status_code == 404


def test_a_file_that_is_not_a_pdf_is_refused(client, store):
    assert upload_bytes(client, b"plain text, not a PDF", name="notes.txt", kind="text/plain").status_code == 415
    assert client.get("/documents").json() == []


def test_a_damaged_pdf_is_refused(client):
    response = upload_bytes(client, b"%PDF-1.7\nthis is not a PDF body\n")
    assert response.status_code == 422
    assert client.get("/documents").json() == []


def test_a_pdf_that_needs_a_password_is_refused(client, tmp_path):
    locked = tmp_path / "locked.pdf"
    with pikepdf.open(sample(tmp_path)) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(user=secrets.token_urlsafe(16), owner=secrets.token_urlsafe(16)))
    response = upload(client, locked)
    assert response.status_code == 422
    assert "password" in response.json()["detail"]


def test_a_file_over_the_limit_is_refused(client, tmp_path, monkeypatch):
    monkeypatch.setattr(core.api, "MAX_UPLOAD_BYTES", 100)
    assert upload(client, sample(tmp_path)).status_code == 413


def test_no_log_line_carries_document_text(client, tmp_path, caplog):
    name = "council-minutes-closed-session.pdf"
    with caplog.at_level(logging.DEBUG):
        document_id = upload(client, sample(tmp_path), name=name).json()["id"]
        findings = client.get(f"/documents/{document_id}/findings").json()
        client.post(f"/findings/{findings[0]['id']}/decision", json={"state": "edited", "proposed_fix": "Annual fee schedule 2026"})
    document_text = [item["evidence"] for item in findings] + [name, "click here", "Annual fee schedule 2026"]
    messages = [record.getMessage() for record in caplog.records]
    assert [text for text in document_text if any(text in message for message in messages)] == []


def test_no_store_is_opened_until_a_request_needs_one():
    get_store.cache_clear()
    app.openapi()
    assert get_store.cache_info().currsize == 0
