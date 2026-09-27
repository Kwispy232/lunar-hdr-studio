"""Build on the OS/architecture being targeted: python build.py."""
import argparse
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lunarhdr import __version__

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--work", default=str(ROOT / "build"))
    args = parser.parse_args()
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--name", "LunarHDR", "--paths", str(ROOT),
        "--additional-hooks-dir", str(ROOT / "packaging" / "hooks"),
        "--distpath", str(Path(args.dist).resolve()),
        "--workpath", str(Path(args.work).resolve() / "pyinstaller"),
        "--specpath", str(Path(args.work).resolve()),
        "--add-data", str(ROOT / "lunarhdr" / "assets") + ":lunarhdr/assets",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQml",
        # Windows scans imported packages for DLLs; Astropy's optional plotting
        # package raises pytest.Skipped when matplotlib is not installed.
        "--exclude-module", "astropy.visualization",
        "--exclude-module", "tkinter",
    ]
    if platform.system() == "Darwin":
        command += ["--osx-bundle-identifier", "studio.lunarhdr.desktop"]
        icon = ROOT / "lunarhdr" / "assets" / "icon.icns"
        if icon.exists():
            command += ["--icon", str(icon)]
    command.append(str(ROOT / "main.py"))
    subprocess.run(command, check=True, cwd=ROOT)
    if platform.system() == "Darwin":
        bundle = Path(args.dist).resolve() / "LunarHDR.app"
        # File-provider folders can recreate Finder metadata during signing.
        # Sign a clean temporary copy, then replace only this freshly built app.
        with tempfile.TemporaryDirectory(prefix="lunarhdr-sign-") as directory:
            staged = Path(directory) / bundle.name
            shutil.copytree(bundle, staged, symlinks=True, copy_function=shutil.copy)
            info_path = staged / "Contents" / "Info.plist"
            with info_path.open("rb") as file:
                info = plistlib.load(file)
            info["CFBundleShortVersionString"] = __version__
            info["CFBundleVersion"] = __version__
            with info_path.open("wb") as file:
                plistlib.dump(info, file)
            subprocess.run(["xattr", "-cr", str(staged)], check=True)
            subprocess.run(["chflags", "-R", "nohidden", str(staged)], check=True)
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(staged)], check=True)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(staged)], check=True)
            archive = bundle.parent / f"LunarHDR-macOS-{platform.machine()}.zip"
            subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(staged), str(archive)], check=True)
            shutil.rmtree(bundle)
            shutil.copytree(staged, bundle, symlinks=True, copy_function=shutil.copy)
    else:
        destination = Path(args.dist).resolve()
        shutil.make_archive(str(destination / f"LunarHDR-{platform.system()}-{platform.machine()}"),
                            "zip", root_dir=destination, base_dir="LunarHDR")


if __name__ == "__main__":
    main()
