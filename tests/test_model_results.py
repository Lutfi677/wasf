import json
import pathlib

import pytest
import recorded_font

from core.model.document import Document

run_model = pytest.importorskip("run_model")
scoring = pytest.importorskip("scoring")

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = ROOT / "eval" / "model.json"
MODEL_LIVE = ROOT / "eval" / "model_live.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def generated():
    if not run_model.MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")


def test_the_committed_model_covers_all_eight_samples():
    assert sorted(load(MODEL)["samples"]) == [f"{number:02d}" for number in range(1, 9)]


def test_every_gate_row_is_met_from_the_model():
    gate = load(MODEL)["gate"]
    assert gate["of"] == 24
    assert gate["open"] == []
    assert gate["met"] == 24


def test_01_text_and_header_cells_reach_their_targets_from_the_model():
    record = load(MODEL)["samples"]["01"]
    assert record["text"]["percent"] == 100.0
    assert record["header_cells"] == {"found": 4, "of": 4, "percent": 100.0}


def test_02_header_cells_reach_the_fixed_target_from_the_model():
    assert load(MODEL)["samples"]["02"]["header_cells"]["percent"] == 100.0
    assert load(MODEL)["gate"]["rows"]["02/header_cells"]["met"]


def test_the_three_parcel_lines_go_to_a_person_from_the_model():
    assert load(MODEL)["samples"]["05"]["parcel_lines_to_person"] == {"found": 3, "of": 3, "percent": 100.0}


def test_the_language_is_right_for_every_sample_whose_key_gives_one_tag():
    tagged = {sample: record["language"] for sample, record in load(MODEL)["samples"].items() if "language" in record}
    assert len(tagged) == 7
    assert all(language["right"] for language in tagged.values())


def test_the_committed_model_holds_no_answer_key_text():
    generated()
    committed = MODEL.read_text(encoding="utf-8").casefold()
    for entry in load(run_model.MANIFEST)["documents"]:
        for text in scoring.key_strings(entry):
            if len(text) >= 5:
                assert text not in committed


def test_the_committed_model_is_reproduced_for_every_sample_not_set_in_another_font():
    generated()
    recorded_font.require_in_ci()
    same_font = recorded_font.uses_recorded_font()
    fresh = run_model.run()
    committed = load(MODEL)
    for number, record in fresh["samples"].items():
        if number != "07" or same_font:
            assert record == committed["samples"][number], number
    if same_font:
        assert fresh["gate"] == committed["gate"]
    else:
        for name, row in fresh["gate"]["rows"].items():
            if not name.startswith("07/"):
                assert row == committed["gate"]["rows"][name], name


def test_two_runs_give_the_same_model():
    generated()
    assert run_model.run() == run_model.run()


def test_the_kept_live_check_validates_every_sample_it_covers():
    if not MODEL_LIVE.is_file():
        pytest.skip("no live check has been run")
    live = load(MODEL_LIVE)
    assert sorted(live["samples"]) == [f"{number:02d}" for number in range(1, 9)]
    for record in live["samples"].values():
        assert record["validates"] is True
        assert set(record["differences"]) == {"blocks", "tables", "figures", "regions"}


def test_differences_count_the_items_that_differ():
    def make(texts):
        blocks = [
            {"id": f"b{i}", "page": 1, "text": text, "box": [0, 0, 5, 5], "reading_order": i, "engine": "x"}
            for i, text in enumerate(texts)
        ]
        return Document.model_validate({"engines": ["x"], "pages": [{"number": 1, "width": 100, "height": 100}], "blocks": blocks})

    assert run_model.differences(make(["a", "b"]), make(["a", "b"]))["blocks"] == 0
    assert run_model.differences(make(["a", "b"]), make(["a", "c"]))["blocks"] == 1
    assert run_model.differences(make(["a", "b", "c"]), make(["a", "b"]))["blocks"] == 1
