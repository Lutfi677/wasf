import json
import pathlib

import pytest
import recorded_font

run_order = pytest.importorskip("run_order")

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORDER = ROOT / "eval" / "order.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def generated():
    if not run_order.MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")


def test_committed_done_when_is_met_for_03_and_07():
    done_when = load(ORDER)["done_when"]
    assert sorted(done_when) == ["03", "07"]
    for sample, metrics in done_when.items():
        for metric, result in metrics.items():
            assert result["met"], (sample, metric, result)


def test_done_when_for_03_is_reproduced():
    generated()
    fresh = run_order.run()
    committed = load(ORDER)
    assert fresh["samples"]["03"] == committed["samples"]["03"]
    assert fresh["done_when"]["03"] == committed["done_when"]["03"]


def test_done_when_for_07_is_reproduced_with_the_recorded_arabic_font():
    generated()
    recorded_font.require_in_ci()
    if not recorded_font.uses_recorded_font():
        pytest.skip("sample 07 was generated with another Arabic font than the recorded results")
    fresh = run_order.run()
    committed = load(ORDER)
    assert fresh["samples"]["07"] == committed["samples"]["07"]
    assert fresh["done_when"]["07"] == committed["done_when"]["07"]
