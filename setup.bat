@echo off
REM Einmalige Einrichtung: erstellt .venv und installiert alle Pakete.
REM Doppelklick genuegt. Ruft setup.ps1 ohne Aenderung der Execution Policy auf.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
pause
