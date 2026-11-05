import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "openapi.json"


def openapi_text() -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.api import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    TARGET.write_text(openapi_text(), encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
