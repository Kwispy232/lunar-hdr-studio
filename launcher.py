"""Prepare a repository-local environment and start the desktop application."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

APP_ROOT = Path(__file__).resolve().parent
PYTHON_HELP = "Install Python 3.11–3.14 from https://www.python.org/downloads/ and try again."


class SetupError(Exception):
    """A recoverable setup problem to display without a traceback."""


def supported_python(version):
    return (3, 11) <= tuple(version[:2]) < (3, 15)


def read_requirements(path):
    requirements = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if not match:
            raise SetupError(f"Unsupported dependency specification in {path.name}: {line}")
        requirements[match[1]] = match[2]
    return requirements


def environment_info(python, packages):
    # Inspect the target environment, not the Python used to run this launcher.
    code = """
import importlib.metadata as metadata
import json, sys
versions = {}
for name in json.loads(sys.argv[1]):
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        versions[name] = None
print(json.dumps({'python': list(sys.version_info[:3]), 'packages': versions}))
"""
    try:
        result = subprocess.run(
            [str(python), "-c", code, json.dumps(list(packages))],
            check=True, capture_output=True, text=True, cwd=APP_ROOT,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise SetupError(
            "The local .venv cannot run. Rename .venv and start again to create a fresh environment."
        ) from exc


def prepare_environment():
    if not supported_python(sys.version_info):
        raise SetupError(PYTHON_HELP)
    environment = APP_ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        if environment.exists():
            raise SetupError(
                "The local .venv is incomplete. Rename .venv and start again to create a fresh environment."
            )
        print("Creating the local Python environment…", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, cwd=APP_ROOT)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SetupError(
                "Could not create .venv. Check that this folder is writable and Python's venv module is installed. "
                "On Debian/Ubuntu, install python3-venv. " + PYTHON_HELP
            ) from exc
    requirements = read_requirements(APP_ROOT / "requirements.txt")
    info = environment_info(python, requirements)
    if not supported_python(info["python"]):
        raise SetupError(
            "The local .venv uses an unsupported Python version. Rename .venv and start again. " + PYTHON_HELP
        )
    missing = [name for name, version in requirements.items() if info["packages"].get(name) != version]
    if missing:
        print("Installing or updating dependencies (internet access is needed): " + ", ".join(missing), flush=True)
        try:
            subprocess.run(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(APP_ROOT / "requirements.txt")],
                check=True, cwd=APP_ROOT,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SetupError(
                "Dependency installation failed. Check the error above, your internet connection, "
                "and available disk space, then start again. " + PYTHON_HELP
            ) from exc
    return python


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        python = prepare_environment()
        if args == ["--check"]:
            print("Lunar HDR environment is ready.")
            return 0
        result = subprocess.run([str(python), str(APP_ROOT / "main.py"), *args], cwd=APP_ROOT)
        if result.returncode:
            print("Lunar HDR could not start. See the error above.", file=sys.stderr)
            if sys.platform.startswith("linux"):
                print(
                    "If Qt reports missing platform libraries, install your distribution's Qt/X11 runtime libraries. "
                    "On Debian/Ubuntu: sudo apt install libegl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0",
                    file=sys.stderr,
                )
        return result.returncode
    except (SetupError, OSError) as exc:
        print(f"Lunar HDR setup: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
