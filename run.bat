@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 goto folder_failure
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] < (3,15)))" >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" launcher.py %*
    goto finished
  )
)
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.11 3.12 3.13 3.14) do (
    py -%%V -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] < (3,15)))" >nul 2>nul
    if not errorlevel 1 (
      py -%%V launcher.py %*
      goto finished
    )
  )
)
for %%P in (python python3) do (
  %%P -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] < (3,15)))" >nul 2>nul
  if not errorlevel 1 (
    %%P launcher.py %*
    goto finished
  )
)
echo Lunar HDR needs Python 3.11-3.14. Install it from https://www.python.org/downloads/ and try again.
set "lunar_exit_code=1"
goto cleanup
:finished
set "lunar_exit_code=%errorlevel%"
:cleanup
popd
if not "%lunar_exit_code%"=="0" if not defined CI pause
exit /b %lunar_exit_code%
:folder_failure
echo Could not open the Lunar HDR folder.
if not defined CI pause
exit /b 1
