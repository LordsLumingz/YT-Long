@echo off
rem YT-Long setup: installs Python if it is missing, then the Python modules.
setlocal
cd /d "%~dp0"

echo === YT-Long setup ===
echo.

call :find_python
if defined PY goto modules

echo Python was not found. Installing it with winget...
winget --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo winget is not available on this PC.
    echo Install Python from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH", then run install.bat again.
    goto fail
)
winget install -e --id Python.Python.3.14 --scope user
if errorlevel 1 (
    echo.
    echo The Python install did not finish.
    goto fail
)

call :find_python
if not defined PY (
    echo.
    echo Python is installed, but this window cannot see it yet.
    echo Close this window and run install.bat again.
    goto fail
)

:modules
echo Using: %PY%
%PY% --version
echo.
echo Installing modules from requirements.txt...
%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo.
    echo Installing the modules failed. Check your internet connection.
    goto fail
)

echo.
%PY% yt_batch.py version
echo Setup finished. Next: put your client_secret_*.json in this folder,
echo then run:  %PY% yt_batch.py ?
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1

:find_python
set "PY="
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python" & exit /b
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3" & exit /b
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%LocalAppData%\Python\pythoncore-3*") do (
    if exist "%%D\python.exe" set PY="%%D\python.exe"
)
exit /b
