import io
import os
import uuid
from functools import lru_cache
from typing import Annotated, Any

import pikepdf
import pypdfium2 as pdfium
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.routing import APIRoute

from core.detectors import detect
from core.findings import Decision, StoredFinding
from core.output.report import render
from core.store import Document, Store, now

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PDF_HEADER = b"%PDF-"
HEADER_WINDOW = 1024
DEFAULT_DB = "data/wasf.sqlite3"
DEFAULT_FILES = "data/documents"
MARKDOWN = "text/markdown"
REPORT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"description": "The report as Markdown", "content": {MARKDOWN: {"schema": {"type": "string"}}}},
}


def operation_id(route: APIRoute) -> str:
    return route.name


app = FastAPI(title="Wasf", version="0.0.0", generate_unique_id_function=operation_id)


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(os.environ.get("WASF_DB", DEFAULT_DB), os.environ.get("WASF_FILES", DEFAULT_FILES))


StoreDependency = Annotated[Store, Depends(get_store)]


def unreadable(detail: str) -> HTTPException:
    return HTTPException(422, detail)


def page_count(data: bytes) -> int:
    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
    except pikepdf.PasswordError:
        raise unreadable("The file needs a password to open") from None
    except pikepdf.PdfError:
        raise unreadable("The file is damaged and cannot be read") from None
    if pages == 0:
        raise unreadable("The file has no pages")
    return pages


@app.post("/documents", status_code=201, response_model=Document)
def upload_document(file: UploadFile, store: StoreDependency) -> Document:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than the upload limit")
    if PDF_HEADER not in data[:HEADER_WINDOW]:
        raise HTTPException(415, "The file is not a PDF")
    pages = page_count(data)
    store.files.mkdir(parents=True, exist_ok=True)
    pending = store.files / f"upload-{uuid.uuid4().hex}.pdf"
    pending.write_bytes(data)
    try:
        findings = detect(pending)
        document = store.add_document(pages, findings)
    except (pikepdf.PdfError, pdfium.PdfiumError):
        pending.unlink(missing_ok=True)
        raise unreadable("The file is damaged and cannot be read") from None
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    pending.replace(store.files / f"{document.id}.pdf")
    return document


@app.get("/documents", response_model=list[Document])
def list_documents(store: StoreDependency) -> list[Document]:
    return store.documents()


@app.get("/documents/{document_id}/findings", response_model=list[StoredFinding])
def list_findings(document_id: int, store: StoreDependency) -> list[StoredFinding]:
    findings = store.findings(document_id)
    if findings is None:
        raise HTTPException(404, "No document with this id")
    return findings


@app.get("/documents/{document_id}/report", response_class=Response, responses=REPORT_RESPONSE)
def get_report(document_id: int, store: StoreDependency) -> Response:
    document = store.document(document_id)
    findings = store.findings(document_id)
    if document is None or findings is None:
        raise HTTPException(404, "No document with this id")
    return Response(render(document, findings, now()), media_type=f"{MARKDOWN}; charset=utf-8")


@app.post("/findings/{finding_id}/decision", response_model=StoredFinding)
def record_decision(finding_id: int, decision: Decision, store: StoreDependency) -> StoredFinding:
    finding = store.record_decision(finding_id, decision)
    if finding is None:
        raise HTTPException(404, "No finding with this id")
    return finding
