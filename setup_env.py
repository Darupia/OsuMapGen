"""First-run setup / repair. Run by "Setup or Repair.bat" with any Python 3.10-3.13.

Creates a private virtual environment in %LOCALAPPDATA%\\OsuMapGen\\venv (short
path, no admin rights), installs the pinned packages from PyPI, and verifies
that everything imports. Nothing outside that folder is modified.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OsuMapGen" / "venv"
MARKER = VENV / "osumapgen-ready.txt"


def say(msg=""):
    print(msg, flush=True)


def venv_python() -> Path:
    return VENV / "Scripts" / "python.exe" if os.name == "nt" else VENV / "bin" / "python"


def run(cmd) -> int:
    say("> " + " ".join(str(c) for c in cmd))
    return subprocess.call([str(c) for c in cmd])


def main() -> int:
    repair = "--repair" in sys.argv
    say("OsuMapGen setup")
    say("=" * 40)
    v = sys.version_info
    if not ((3, 10) <= (v.major, v.minor) <= (3, 13)):
        say(f"Python {v.major}.{v.minor} is not supported. Please install Python 3.12 from https://www.python.org "
            "(tick 'Add python.exe to PATH') and run this again.")
        return 1
    say(f"Using Python {v.major}.{v.minor}.{v.micro} at {sys.executable}")

    if repair and VENV.exists():
        say(f"Removing the old environment at {VENV} ...")
        shutil.rmtree(VENV, ignore_errors=True)
    if not venv_python().exists():
        say(f"Creating private environment at {VENV} ...")
        VENV.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
    py = venv_python()
    if run([py, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"]) != 0:
        say("Warning: could not upgrade pip; continuing with the bundled version.")
    if run([py, "-m", "pip", "install", "--disable-pip-version-check", "-r", HERE / "requirements.txt"]) != 0:
        say("")
        say("Package installation failed. The most common causes are:")
        say("  - no internet connection (packages come from pypi.org), or")
        say("  - a Python version without prebuilt packages (use Python 3.12).")
        say("Fix that, then double-click 'Setup or Repair.bat' again.")
        return 1
    say("Verifying ...")
    if run([py, "-m", "osumapgen", "--check"]) != 0:
        say("Verification failed: see the messages above. Running 'Setup or Repair.bat' again rebuilds everything.")
        return 1
    MARKER.write_text(str(HERE), encoding="utf-8")
    say("")
    say("Setup complete. Start the app with 'Start OsuMapGen.bat'.")
    return 0


if __name__ == "__main__":
    os.chdir(HERE)
    sys.exit(main())
