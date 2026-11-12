import argparse
import json
import sys
import time
from typing import Any

from core.extract import service_dict
from providers.azure import cu, cu_provider, support

ROOT = support.ROOT
SAMPLES = ROOT / "eval" / "samples" / "pdfs"
LIVE = ROOT / "eval" / "fixtures" / "live"
RETRY_WAIT = 60
NOTE = "phase 2 step 6; live model check"


def analyze_once_more_on_failure(client: Any, data: bytes) -> tuple[dict[str, Any], dict[str, Any], float] | None:
    for attempt in (1, 2):
        try:
            return cu.analyze(client, service_dict.LAYOUT, data)
        except Exception as error:
            print(f"  attempt {attempt} failed: {support.describe(error)}")
            if attempt == 1:
                time.sleep(RETRY_WAIT)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch prebuilt-layout responses live and keep them for the model check")
    parser.add_argument("--sample", action="append", help="sample id such as 01; repeat for more; default all")
    parser.add_argument("--refresh", action="store_true", help="call again even when a live response is kept")
    args = parser.parse_args()

    config = support.read_config()
    ceiling = int(config["CU_MAX_CALLS"])
    samples = sorted(path.name[:2] for path in SAMPLES.glob("*.pdf"))
    if args.sample:
        samples = [sample for sample in samples if sample in args.sample]
    pending = [sample for sample in samples if args.refresh or not (LIVE / f"{sample}.json").is_file()]
    if not pending:
        print("Nothing to fetch: every live response is kept. Use --refresh to call again.")
        return 0
    if len(pending) > ceiling:
        print(f"Refused: {len(pending)} calls planned, ceiling CU_MAX_CALLS is {ceiling}")
        return 2
    print(f"{len(pending)} live calls planned, ceiling {ceiling}")

    client = cu.make_client(config["CONTENTUNDERSTANDING_ENDPOINT"])
    LIVE.mkdir(parents=True, exist_ok=True)
    for sample in pending:
        path = next(SAMPLES.glob(f"{sample}_*.pdf"))
        outcome = analyze_once_more_on_failure(client, path.read_bytes())
        if outcome is None:
            print(f"Stopped at {sample} after one retry")
            return 1
        response, usage, seconds = outcome
        (LIVE / f"{sample}.json").write_text(json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        support.log_cost(service_dict.LAYOUT, usage, f"{NOTE}; sample {sample}")
        answer = (response, usage, seconds)
        provider = cu_provider.ContentUnderstandingProvider(lambda _data, answer=answer: answer)
        read = provider.read(path)
        print(f"{sample}: {seconds:.1f} s, pages {support.page_total(usage)}, blocks {len(read['blocks'])}, tables {len(read['tables'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
