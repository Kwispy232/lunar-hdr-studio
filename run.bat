@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto install
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -c "import sys; assert sys.version_info >= (3,11), 'Install Python 3.11 or newer'"
if errorlevel 1 goto failure
py -3 -m venv .venv
goto install
:usepython
python -c "import sys; assert sys.version_info >= (3,11), 'Install Python 3.11 or newer'"
if errorlevel 1 goto failure
python -m venv .venv
:install
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 goto failure
.venv\Scripts\python.exe main.py
if errorlevel 1 goto failure
exit /b 0
:failure
echo Lunar HDR could not start. Install Python 3.11+ from python.org and try again.
pause
exit /b 1
