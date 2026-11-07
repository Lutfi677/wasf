import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from core.findings import Decision, Finding, Source, State, StoredFinding

MEMORY = ":memory:"
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    pages INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents (id),
    position INTEGER NOT NULL,
    defect TEXT NOT NULL,
    page INTEGER,
    evidence TEXT NOT NULL,
    source TEXT NOT NULL,
    state TEXT NOT NULL,
    proposed_fix TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES findings (id),
    state TEXT NOT NULL,
    proposed_fix TEXT,
    decided_at TEXT NOT NULL
);
"""
DOCUMENTS = """
SELECT documents.id, documents.pages, documents.uploaded_at, COUNT(findings.id) AS findings
FROM documents LEFT JOIN findings ON findings.document_id = documents.id
GROUP BY documents.id ORDER BY documents.id
"""
DOCUMENT = """
SELECT documents.id, documents.pages, documents.uploaded_at, COUNT(findings.id) AS findings
FROM documents LEFT JOIN findings ON findings.document_id = documents.id
WHERE documents.id = ? GROUP BY documents.id
"""


class Document(BaseModel):
    id: int
    pages: int
    findings: int
    uploaded_at: datetime


def now() -> datetime:
    return datetime.now(UTC)


def document(row: sqlite3.Row) -> Document:
    return Document(id=row["id"], pages=row["pages"], findings=row["findings"], uploaded_at=datetime.fromisoformat(row["uploaded_at"]))


def stored(row: sqlite3.Row) -> StoredFinding:
    return StoredFinding(
        id=row["id"],
        document_id=row["document_id"],
        defect=row["defect"],
        page=row["page"],
        evidence=row["evidence"],
        source=Source(row["source"]),
        state=State(row["state"]),
        proposed_fix=row["proposed_fix"],
    )


class Store:
    def __init__(self, database: str | Path, files: str | Path):
        self.files = Path(files)
        if str(database) != MEMORY:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(str(database), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def add_document(self, pages: int, findings: list[Finding]) -> Document:
        uploaded_at = now()
        rows = [
            (position, item.defect, item.page, item.evidence, item.source.value, item.state.value, item.proposed_fix)
            for position, item in enumerate(findings)
        ]
        with self.lock, self.connection:
            inserted = self.connection.execute(
                "INSERT INTO documents (pages, uploaded_at) VALUES (?, ?) RETURNING id", (pages, uploaded_at.isoformat())
            ).fetchone()
            document_id: int = inserted["id"]
            self.connection.executemany(
                "INSERT INTO findings (document_id, position, defect, page, evidence, source, state, proposed_fix)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(document_id, *row) for row in rows],
            )
        return Document(id=document_id, pages=pages, findings=len(findings), uploaded_at=uploaded_at)

    def documents(self) -> list[Document]:
        with self.lock:
            rows = self.connection.execute(DOCUMENTS).fetchall()
        return [document(row) for row in rows]

    def document(self, document_id: int) -> Document | None:
        with self.lock:
            row = self.connection.execute(DOCUMENT, (document_id,)).fetchone()
        return None if row is None else document(row)

    def findings(self, document_id: int) -> list[StoredFinding] | None:
        with self.lock:
            if self.connection.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
                return None
            rows = self.connection.execute("SELECT * FROM findings WHERE document_id = ? ORDER BY position", (document_id,)).fetchall()
        return [stored(row) for row in rows]

    def record_decision(self, finding_id: int, decision: Decision) -> StoredFinding | None:
        decided_at = now().isoformat()
        with self.lock, self.connection:
            row = self.connection.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if row is None:
                return None
            fix = decision.proposed_fix if decision.state is State.edited else row["proposed_fix"]
            self.connection.execute("UPDATE findings SET state = ?, proposed_fix = ? WHERE id = ?", (decision.state.value, fix, finding_id))
            self.connection.execute(
                "INSERT INTO decisions (finding_id, state, proposed_fix, decided_at) VALUES (?, ?, ?, ?)",
                (finding_id, decision.state.value, decision.proposed_fix, decided_at),
            )
            row = self.connection.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        return stored(row)

    def decisions(self, finding_id: int) -> list[dict]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT state, proposed_fix, decided_at FROM decisions WHERE finding_id = ? ORDER BY id", (finding_id,)
            ).fetchall()
        return [dict(row) for row in rows]
