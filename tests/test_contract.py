import json
import pathlib

import pytest

from core.api import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "openapi.json"
EXPORT = "run python scripts/export_openapi.py"
OPERATIONS = {
    ("post", "/documents"): "upload_document",
    ("get", "/documents"): "list_documents",
    ("get", "/documents/{document_id}/findings"): "list_findings",
    ("post", "/findings/{finding_id}/decision"): "record_decision",
}
FINDING_FIELDS = {"defect", "page", "evidence", "source", "state", "proposed_fix"}
STATES = ["proposed", "approved", "edited", "rejected", "escalated"]


@pytest.fixture(scope="module")
def committed():
    assert CONTRACT.is_file(), f"openapi.json is missing: {EXPORT}"
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_committed_contract_matches_the_app(committed):
    assert committed == json.loads(json.dumps(app.openapi())), f"openapi.json is out of date: {EXPORT}"


def test_contract_lists_the_four_operations(committed):
    paths = committed["paths"]
    found = {(method, path): operation["operationId"] for path, methods in paths.items() for method, operation in methods.items()}
    assert found == OPERATIONS


def test_contract_carries_the_models(committed):
    schemas = committed["components"]["schemas"]
    assert set(schemas["StoredFinding"]["properties"]) == FINDING_FIELDS | {"id", "document_id"}
    assert schemas["State"]["enum"] == STATES
    assert schemas["Source"]["enum"] == ["rule", "model"]
    assert set(schemas["Decision"]["properties"]) == {"state", "proposed_fix"}
    assert set(schemas["Document"]["properties"]) == {"id", "pages", "findings", "uploaded_at"}
