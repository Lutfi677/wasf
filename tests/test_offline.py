import importlib
import json
import os
import pathlib
import socket
import sys

import pytest
import recorded_font

run_bakeoff = pytest.importorskip("run_bakeoff")
run_rules = pytest.importorskip("run_rules")
run_order = pytest.importorskip("run_order")
run_scans = pytest.importorskip("run_scans")
run_model = pytest.importorskip("run_model")

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CREDENTIAL_PREFIXES = ("AZURE_", "CONTENTUNDERSTANDING_", "FOUNDRY_", "OPENAI_", "APPLICATIONINSIGHTS_", "IDENTITY_", "MSI_")
SDK_PACKAGES = ("azure", "openai")
FONT_INDEPENDENT = ["01", "02", "03", "04", "05", "06"]


def refuse(*args, **kwargs):
    raise AssertionError("an offline test reached for the network")


def go_offline(monkeypatch, empty_folder):
    for name in list(os.environ):
        if name.upper().startswith(CREDENTIAL_PREFIXES):
            monkeypatch.delenv(name)
    monkeypatch.setenv("AZURE_CONFIG_DIR", str(empty_folder))
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for package in SDK_PACKAGES:
        for name in [name for name in sys.modules if name == package or name.startswith(package + ".")]:
            monkeypatch.delitem(sys.modules, name)
        monkeypatch.setitem(sys.modules, package, None)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    go_offline(monkeypatch, tmp_path)


def load(name):
    return json.loads((EVAL / name).read_text(encoding="utf-8"))


def generated():
    if not run_model.MANIFEST.is_file():
        pytest.skip("eval/samples has not been generated")


def recorded_font_or_skip():
    generated()
    recorded_font.require_in_ci()
    if not recorded_font.uses_recorded_font():
        pytest.skip("sample 07 was generated in another Arabic font than the recorded results")


def test_in_ci_another_arabic_font_fails_instead_of_skipping(monkeypatch):
    monkeypatch.setattr(recorded_font, "uses_recorded_font", lambda: False)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="cannot be checked in CI"):
        recorded_font.require_in_ci()


def test_outside_ci_another_arabic_font_does_not_fail(monkeypatch):
    monkeypatch.setattr(recorded_font, "uses_recorded_font", lambda: False)
    monkeypatch.delenv("CI", raising=False)
    recorded_font.require_in_ci()


def test_the_guard_removes_credentials_and_points_the_cli_at_an_empty_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "x")
    monkeypatch.setenv("foundry_project_endpoint", "x")
    monkeypatch.setenv("WASF_DB", "kept")
    go_offline(monkeypatch, tmp_path)
    assert not [name for name in os.environ if name.upper().startswith(CREDENTIAL_PREFIXES) and name != "AZURE_CONFIG_DIR"]
    assert os.environ["AZURE_CONFIG_DIR"] == str(tmp_path)
    assert os.environ["WASF_DB"] == "kept"


def test_the_guard_refuses_a_connection(offline):
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)
    with pytest.raises(AssertionError, match="network"):
        socket.socket().connect(("127.0.0.1", 9))


@pytest.mark.parametrize("name", ["azure", "azure.identity", "azure.ai.contentunderstanding", "openai"])
def test_the_guard_refuses_the_sdks(offline, name):
    with pytest.raises(ImportError):
        importlib.import_module(name)


def test_the_bake_off_runs_offline(offline):
    generated()
    assert run_bakeoff.run() == load("bakeoff.json")


def test_the_structure_rules_run_offline(offline):
    generated()
    recorded_font.require_in_ci()
    fresh = run_rules.run()["samples"]
    committed = load("rules.json")["samples"]
    samples = sorted(committed) if recorded_font.uses_recorded_font() else FONT_INDEPENDENT
    for sample in samples:
        assert fresh[sample] == committed[sample], sample


def test_the_reading_order_runs_offline(offline):
    recorded_font_or_skip()
    assert run_order.run() == load("order.json")


def test_the_scans_run_offline(offline):
    assert run_scans.run() == load("scans.json")


def test_the_document_model_runs_offline(offline):
    recorded_font_or_skip()
    assert run_model.run() == load("model.json")


def test_the_whole_phase_ran_without_loading_an_sdk(offline):
    generated()
    run_model.run()
    run_scans.run()
    loaded = [name for name in sys.modules if name.split(".")[0] in SDK_PACKAGES and sys.modules[name] is not None]
    assert loaded == []
