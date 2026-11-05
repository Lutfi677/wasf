from __future__ import annotations

import _env

_env.load()
_env.require("CONTENTUNDERSTANDING_ENDPOINT")

try:
    from azure.ai.contentunderstanding import ContentUnderstandingClient
    from azure.identity import DefaultAzureCredential
except ImportError as exc:  # pragma: no cover - environment problem, not a logic problem
    raise SystemExit(
        f"Missing package ({exc.name}). Run: pip install -e '.[azure]'"
    ) from None

MAPPINGS = {
    "gpt-5.2": "gpt-5.2",
    "text-embedding-3-large": "text-embedding-3-large",
    "prebuilt-analyzer-completion": "gpt-5.2",
    "prebuilt-analyzer-completion-mini": "gpt-5.2",
    "prebuilt-analyzer-embedding": "text-embedding-3-large",
}

def main() -> int:
    import os

    client = ContentUnderstandingClient(
        endpoint=os.environ["CONTENTUNDERSTANDING_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    client.update_defaults(model_deployments=MAPPINGS)

    current = client.get_defaults().model_deployments
    print("Mappings now set on the resource:")
    for key, value in current.items():
        print(f"  {key:38s} -> {value}")
    if len(current) < len(MAPPINGS):
        print(f"\nGATE NOT PASSED: expected {len(MAPPINGS)} mappings, found {len(current)}.")
        return 1
    print(f"\nGate passed: {len(current)} mappings listed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
