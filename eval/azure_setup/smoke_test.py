from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

import _env

_env.load()

try:
    from azure.ai.contentunderstanding import ContentUnderstandingClient
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
except ImportError as exc:  # pragma: no cover - environment problem, not a logic problem
    raise SystemExit(
        f"Missing package ({exc.name}). Run: pip install -e '.[azure]'"
    ) from None

COST_LOG = _env.REPO_ROOT / "eval" / "cost_log.jsonl"
DEFAULT_PDF = _env.REPO_ROOT / "eval" / "samples" / "pdfs" / "01_county_budget_summary.pdf"

def log_cost(service: str, deployment: str, tokens_in, tokens_out, pages, note: str) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": 0,
        "service": service,
        "deployment": deployment,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "pages": pages,
        "note": note,
    }
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COST_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")

def hint_for(exc: Exception) -> str:
    low = f"{type(exc).__name__} {exc}".lower()
    if any(word in low for word in ("401", "403", "forbidden", "unauthorized", "permission", "authorization")):
        return "Role assignments can take 5 to 10 minutes to apply. Wait, run `az login` again, retry."
    if "deploymentnotfound" in low or "404" in low:
        return "The deployment name or endpoint is wrong. Check config/azure.env and `az cognitiveservices account deployment list`."
    if "429" in low or "ratelimit" in low:
        return "Rate limited: the deployment capacity is small. Wait a minute and retry."
    if "credential" in low or "az login" in low:
        return "Not signed in for this tenant. Run: az login --tenant <your tenant id>"
    return "Read the message above; if unclear, send it to me unchanged."

def model_call(credential, model: str) -> bool:
    print(f"\n[1/2] Model call: {model}")
    try:
        project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential)
        client = project.get_openai_client()
        reply = client.responses.create(
            model=model,
            input="Reply with the single word: ready",
            max_output_tokens=5000,
            store=False,
        )
        usage = reply.usage
        print(f"      reply: {reply.output_text.strip()!r} | tokens in={usage.input_tokens} "
              f"out={usage.output_tokens} total={usage.total_tokens}")
        log_cost("model", model, usage.input_tokens, usage.output_tokens, None, "smoke test")
        return True
    except Exception as exc:  # noqa: BLE001 - a smoke test must report, not crash
        print(f"      FAILED: {type(exc).__name__}: {exc}\n      Hint: {hint_for(exc)}")
        return False

def layout_call(credential, pdf_path: pathlib.Path) -> bool:
    print(f"\n[2/2] Content Understanding prebuilt-layout on {pdf_path.name}")
    if not pdf_path.exists():
        print(f"      FAILED: {pdf_path} not found. Pass --pdf with any small PDF.")
        return False
    try:
        client = ContentUnderstandingClient(
            endpoint=os.environ["CONTENTUNDERSTANDING_ENDPOINT"], credential=credential)
        poller = client.begin_analyze_binary(analyzer_id="prebuilt-layout", binary_input=pdf_path.read_bytes())
        content = poller.result().contents[0]
        pages = len(content.pages or [])
        print(f"      layout: {pages} pages, {len(content.tables or [])} tables, {len(content.figures or [])} figures")
        usage = getattr(poller, "usage", None)
        usage_note = usage.as_dict() if hasattr(usage, "as_dict") else usage
        print(f"      usage reported by the SDK: {usage_note}")
        log_cost("content-understanding", "prebuilt-layout", None, None, pages, f"smoke test; usage={usage_note}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"      FAILED: {type(exc).__name__}: {exc}\n      Hint: {hint_for(exc)}")
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test: one model call and one prebuilt-layout call, both without a key")
    parser.add_argument("--pdf", type=pathlib.Path, default=DEFAULT_PDF, help="PDF for the layout call")
    parser.add_argument("--model", default="gpt-5-mini", help="deployment name for the model call")
    args = parser.parse_args()

    _env.require("FOUNDRY_PROJECT_ENDPOINT", "CONTENTUNDERSTANDING_ENDPOINT")
    credential = DefaultAzureCredential()

    results = {
        "model call": model_call(credential, args.model),
        "layout call": layout_call(credential, args.pdf),
    }
    print("\nSummary: " + ", ".join(f"{name}: {'ok' if ok else 'FAILED'}" for name, ok in results.items()))
    if all(results.values()):
        print(f"Gate passed: both calls succeeded with no key. Rows appended to {COST_LOG.relative_to(_env.REPO_ROOT)}")
        return 0
    if results["model call"] and not results["layout call"]:
            print(f"The layout call was not attempted: {args.pdf} does not exist. Pass --pdf with a real file.")
    else:
            print("Layout failed but the model call worked: check the Cognitive Services User role on the RESOURCE.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
