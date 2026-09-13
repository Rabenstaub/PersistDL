@echo off
rem Startet PersistDL MIT sichtbarer Konsole, um Fehler zu sehen.
cd /d "%~dp0"
echo Python-Version:
python --version
echo.
python PersistDL.pyw
echo.
echo --- Programm beendet (Exitcode %errorlevel%) ---
if exist persistdl_error.log (
    echo Inhalt von persistdl_error.log:
    type persistdl_error.log
)
pause
