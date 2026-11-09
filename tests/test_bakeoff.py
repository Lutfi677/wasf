import json
import pathlib

import pytest

scoring = pytest.importorskip("scoring")
run_bakeoff = pytest.importorskip("run_bakeoff")

ROOT = pathlib.Path(__file__).resolve().parent.parent
BAKEOFF = ROOT / "eval" / "bakeoff.json"
FIXTURES = ROOT / "eval" / "fixtures" / "cu"
RUNS = FIXTURES / "runs.json"
MANIFEST = ROOT / "eval" / "samples" / "answer_key" / "manifest.json"
SAMPLES = [f"{n:02d}" for n in range(1, 9)]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def manifest():
    if not MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")
    return load(MANIFEST)


def test_every_analyzer_and_sample_has_a_fixture_and_a_run():
    calls = load(RUNS)["calls"]
    for analyzer in run_bakeoff.ANALYZERS:
        for sample in SAMPLES:
            assert (FIXTURES / analyzer / f"{sample}.json").is_file()
            assert f"{analyzer}/{sample}" in calls


def test_runs_hold_counts_only():
    for call in load(RUNS)["calls"].values():
        assert set(call) == {"recorded", "seconds", "usage"}
        assert isinstance(call["seconds"], float)
        for name, value in call["usage"].items():
            if name == "tokens":
                assert all(isinstance(count, int) for count in value.values())
            else:
                assert isinstance(value, (int, float)), name


def test_bakeoff_is_reproduced_from_the_fixtures():
    manifest()
    assert load(BAKEOFF) == run_bakeoff.run()


def test_bakeoff_holds_no_answer_key_text():
    committed = BAKEOFF.read_text(encoding="utf-8").casefold()
    for entry in manifest()["documents"]:
        for text in scoring.key_strings(entry):
            if len(text) >= 5:
                assert text not in committed
