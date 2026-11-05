import json

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from core.findings import Finding, Source, State

FIELDS = {"defect", "page", "evidence", "source", "state", "proposed_fix"}
STATES = ["proposed", "approved", "edited", "rejected", "escalated"]
SOURCES = ["rule", "model"]


def test_rule_finding_defaults():
    finding = Finding(defect="NO_TAGS", evidence="No structure tree")
    assert finding.page is None
    assert finding.source is Source.rule
    assert finding.state is State.proposed
    assert finding.proposed_fix is None


def test_round_trips_through_json():
    finding = Finding(defect="LOW_CONTRAST", page=2, evidence="Ratio 2.95", state=State.escalated, proposed_fix="Darker footer")
    assert Finding.model_validate_json(finding.model_dump_json()) == finding


def test_json_schema_lists_fields_and_states():
    schema = json.loads(json.dumps(Finding.model_json_schema()))
    assert set(schema["properties"]) == FIELDS
    assert set(schema["required"]) == {"defect", "evidence"}
    assert schema["$defs"]["State"]["enum"] == STATES
    assert schema["$defs"]["Source"]["enum"] == SOURCES


def test_schema_appears_in_openapi_document():
    app = FastAPI()

    @app.get("/findings", response_model=list[Finding])
    def findings() -> list[Finding]:
        return []

    schemas = json.loads(json.dumps(app.openapi()))["components"]["schemas"]
    assert set(schemas["Finding"]["properties"]) == FIELDS
    assert schemas["State"]["enum"] == STATES
    assert schemas["Source"]["enum"] == SOURCES


@pytest.mark.parametrize("change", [{"page": 0}, {"state": "applied"}, {"source": "rules"}])
def test_refuses_invalid_values(change):
    with pytest.raises(ValidationError):
        Finding(defect="NO_LANG", evidence="No document language", **change)
