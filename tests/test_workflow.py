import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
FORBIDDEN = {
    "upload-artifact": re.compile(r"upload-artifact"),
    "azure/login": re.compile(r"azure/login"),
    "secrets.": re.compile(r"(?<![\w.])secrets\."),
}


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_workflow_does_not_contain(name):
    assert not FORBIDDEN[name].search(workflow_text())


def test_secret_baseline_file_name_is_not_a_secret_reference():
    assert not FORBIDDEN["secrets."].search("detect-secrets-hook --baseline .secrets.baseline")
    assert FORBIDDEN["secrets."].search("token: ${{ secrets.TOKEN }}")


def test_token_permissions_are_read_only():
    text = workflow_text()
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)
    assert not re.search(r":\s*write\s*$", text, re.MULTILINE)


def test_every_action_is_pinned_by_full_sha():
    references = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)\s*$", workflow_text(), re.MULTILINE)
    assert references
    for reference in references:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", reference), reference


def test_python_version_meets_requires_python():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = re.match(r">=\s*(\d+)\.(\d+)", pyproject["project"]["requires-python"])
    assert declared is not None
    minimum = tuple(int(part) for part in declared.groups())
    chosen = re.search(r'python-version:\s*"(\d+)\.(\d+)"', workflow_text())
    assert chosen is not None
    assert tuple(int(part) for part in chosen.groups()) >= minimum


def test_workflow_has_no_comment_lines():
    assert not [line for line in workflow_text().splitlines() if line.lstrip().startswith("#")]
