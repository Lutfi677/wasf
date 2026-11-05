from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class State(StrEnum):
    proposed = "proposed"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"
    escalated = "escalated"


class Source(StrEnum):
    rule = "rule"
    model = "model"


class Finding(BaseModel):
    defect: str
    page: int | None = Field(default=None, ge=1)
    evidence: str
    source: Source = Source.rule
    state: State = State.proposed
    proposed_fix: str | None = None


class StoredFinding(Finding):
    id: int
    document_id: int


class Decision(BaseModel):
    state: State
    proposed_fix: str | None = None

    @model_validator(mode="after")
    def check_fix(self) -> Self:
        if self.state is State.proposed:
            raise ValueError("Only Wasf sets a finding to proposed")
        if self.state is State.edited:
            if self.proposed_fix is None or not self.proposed_fix.strip():
                raise ValueError("An edited decision needs the fixed text")
        elif self.proposed_fix is not None:
            raise ValueError("Only an edited decision carries a fix")
        return self
