"""Portable source startup without network access or dependency reinstallation."""
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

import launcher


@pytest.fixture
def source_checkout(tmp_path):
    root = tmp_path / "fresh checkout with spaces"
    root.mkdir()
    source = Path(launcher.__file__).parent
    for name in ("launcher.py", "run.sh", "run.command", "run.bat"):
        shutil.copy2(source / name, root / name)
    pytest_version = importlib.metadata.version("pytest")
    (root / "requirements.txt").write_text(f"pytest=={pytest_version}\n", encoding="utf-8")
    (root / "main.py").write_text(
        "import json, os, sys, pytest\n"
        "print(json.dumps({'cwd': os.getcwd(), 'args': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    environment = root / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = subprocess.check_output(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True
    ).strip()
    # Reuse the test runner's installed packages; the test venv has no pip, so
    # successful startup also demonstrates that no installer was invoked.
    installed_site = importlib.metadata.distribution("pytest").locate_file("")
    (Path(site) / "test-dependencies.pth").write_text(str(installed_site) + "\n", encoding="utf-8")
    return root


def run_entry(root, entry, *args):
    command = [str(root / entry), *args]
    if os.name == "nt":
        # cmd /s /c strips one pair of outer quotes, preserving the quoted
        # batch path and arguments even when both contain spaces.
        shell = subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe")])
        command = f'{shell} /d /s /c "{subprocess.list2cmdline(command)}"'
    return subprocess.run(
        command, cwd=root.parent, env={**os.environ, "CI": "true"},
        text=True, capture_output=True, timeout=30,
    )


@pytest.mark.parametrize("entry", ["run.bat"] if os.name == "nt" else ["run.sh", "run.command"])
def test_source_entry_reuses_environment_from_another_directory(source_checkout, entry):
    result = run_entry(source_checkout, entry, "--smoke-test", "argument with spaces")
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert Path(output["cwd"]) == source_checkout
    assert output["args"] == ["--smoke-test", "argument with spaces"]
    assert "Installing" not in result.stdout


def test_check_prepares_without_launching_application(source_checkout):
    entry = "run.bat" if os.name == "nt" else "run.sh"
    (source_checkout / "main.py").write_text("raise AssertionError('GUI must not start')\n", encoding="utf-8")
    result = run_entry(source_checkout, entry, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "environment is ready" in result.stdout
    assert "Installing" not in result.stdout


@pytest.mark.parametrize("version,expected", [((3, 10, 9), False), ((3, 11, 0), True), ((3, 14, 0), True), ((3, 15, 0), False)])
def test_python_versions_match_pinned_qt_support(version, expected):
    assert launcher.supported_python(version) is expected


def test_incomplete_environment_is_preserved_with_actionable_error(tmp_path, monkeypatch):
    environment = tmp_path / ".venv"
    environment.mkdir()
    marker = environment / "existing-data"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(launcher, "APP_ROOT", tmp_path)
    with pytest.raises(launcher.SetupError, match="Rename .venv"):
        launcher.prepare_environment()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_dependency_change_installs_current_requirements(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "APP_ROOT", tmp_path)
    python = tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    requirement_file = tmp_path / "requirements.txt"
    requirement_file.write_text("numpy==2.4.6\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "environment_info", lambda *args: {"python": [3, 11, 9], "packages": {"numpy": "2.3.0"}})
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    assert launcher.prepare_environment() == python
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:4] == [str(python), "-m", "pip", "install"]
    assert command[-2:] == ["-r", str(requirement_file)]
    assert kwargs["cwd"] == tmp_path


def test_dependency_installation_failure_is_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "APP_ROOT", tmp_path)
    python = tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / "requirements.txt").write_text("numpy==2.4.6\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "environment_info", lambda *args: {"python": [3, 11, 9], "packages": {}})

    def failed_install(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(launcher.subprocess, "run", failed_install)
    assert launcher.main(["--check"]) == 1
    error = capsys.readouterr().err
    assert "Dependency installation failed" in error
    assert "internet connection" in error
    assert "Traceback" not in error


def test_first_launch_creates_local_environment_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "APP_ROOT", tmp_path)
    (tmp_path / "requirements.txt").write_text("# No external dependencies in this fixture\n", encoding="utf-8")
    assert not (tmp_path / ".venv").exists()
    assert launcher.main(["--check"]) == 0
    assert (tmp_path / ".venv" / "pyvenv.cfg").is_file()
    output = capsys.readouterr().out
    assert "Creating" in output
    assert "environment is ready" in output
    assert "Installing" not in output
