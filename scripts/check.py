import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "eval" / "samples"
TOOLS = ROOT / "eval" / "samples_tools"

COMMANDS = (
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "pyright", "--pythonpath", sys.executable],
    [sys.executable, "-m", "pytest"],
)

SAMPLE_COMMANDS = (
    [sys.executable, str(TOOLS / "check_pdf.py")],
    [sys.executable, str(TOOLS / "check_manifest.py")],
    [sys.executable, str(TOOLS / "fingerprint.py"), "compare", str(ROOT / "eval" / "expected" / "fingerprint.json"), str(SAMPLES)],
)


def main() -> int:
    commands = list(COMMANDS)
    if (SAMPLES / "answer_key" / "manifest.json").is_file():
        commands.extend(SAMPLE_COMMANDS)
    else:
        print("Sample checkers skipped: eval/samples has not been generated. Run: python eval/samples_tools/make_samples.py")
    status = 0
    dotnet = shutil.which("dotnet")
    if dotnet:
        commands.append([dotnet, "build", str(ROOT / "AppHost"), "--nologo"])
    else:
        print("C# build skipped: dotnet is not on the PATH. Install the .NET SDK named in global.json")
        if os.environ.get("CI"):
            status = 1
    for command in commands:
        code = subprocess.call(command, cwd=ROOT)
        if code and not status:
            status = code
    return status


if __name__ == "__main__":
    sys.exit(main())
