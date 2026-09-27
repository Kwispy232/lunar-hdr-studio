"""Collect Astropy without importing optional plotting or test packages.

The upstream all-submodules hook imports wcsaxes, which raises pytest's Skipped
exception when pytest is installed but the optional matplotlib package is not.
Lunar HDR uses FITS I/O; no plotting backend is required.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def keep_module(name):
    return ".tests" not in name and not name.startswith("astropy.visualization")


datas = collect_data_files("astropy", excludes=["**/tests/**"])
datas += [
    item for item in collect_data_files("astropy", include_py_files=True)
    if item[0].endswith(("_parsetab.py", "_lextab.py"))
]
datas += copy_metadata("astropy") + copy_metadata("numpy")
hiddenimports = collect_submodules("astropy", filter=keep_module)
hiddenimports += ["numpy.lib.recfunctions"]
