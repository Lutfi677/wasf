from datetime import UTC, datetime

from core.findings import State, StoredFinding
from core.output import words
from core.store import Document

GROUPS = {
    words.APPROVED: (State.approved, State.edited),
    words.OPEN: (State.proposed, State.escalated),
    words.REJECTED: (State.rejected,),
}


def counted(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def where(finding: StoredFinding) -> str:
    return "whole document" if finding.page is None else f"page {finding.page}"


def table(findings: list[StoredFinding]) -> list[str]:
    if not findings:
        return [words.NONE]
    rows = ["| Finding | Rule | Where | State |", "| --- | --- | --- | --- |"]
    rows.extend(f"| {item.id} | `{item.defect}` | {where(item)} | {item.state.value} |" for item in findings)
    return rows


def render(document: Document, findings: list[StoredFinding], written_at: datetime) -> str:
    groups = {name: [item for item in findings if item.state in states] for name, states in GROUPS.items()}
    written = written_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# {words.TITLE}",
        "",
        f"Document {document.id}, {counted(document.pages, 'page')}, {counted(len(findings), 'finding')}. Written {written}.",
        "",
        "| State | Findings |",
        "| --- | --- |",
        *(f"| {name} | {len(group)} |" for name, group in groups.items()),
    ]
    for name, group in groups.items():
        lines.extend(["", f"## {name}", "", *table(group)])
    lines.extend(["", f"## {words.NOT_CLAIMED}", "", words.DISCLAIMER, ""])
    return "\n".join(lines)
