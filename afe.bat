@echo off
REM Startet die Auswertung mit der Python-Umgebung aus .venv, ohne sie zu aktivieren.
REM Beispiele:  afe.bat all   |   afe.bat import data\raw\export.sql   |   afe.bat notebook
setlocal
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo .venv fehlt. Bitte zuerst setup.bat ausfuehren.
    exit /b 1
)
if /I "%~1"=="notebook" (
    "%~dp0.venv\Scripts\jupyter-lab.exe" --notebook-dir="%~dp0notebooks"
    exit /b %ERRORLEVEL%
)
"%VENV_PY%" -m afe %*
exit /b %ERRORLEVEL%
