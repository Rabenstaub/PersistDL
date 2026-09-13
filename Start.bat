@echo off
rem PersistDL v1.6.1 - Starter
cd /d "%~dp0"

if exist ".deps_ok" goto run

echo Installiere Abhaengigkeiten - einmalig ...
echo Ausgabe wird in install_log.txt gespeichert.
python -m pip install --upgrade PyQt6 requests > install_log.txt 2>&1
type install_log.txt
if errorlevel 1 goto fail
echo ok > .deps_ok

:run
start "" pythonw PersistDL.pyw
exit /b 0

:fail
echo.
echo FEHLER: Installation fehlgeschlagen - Details siehe install_log.txt
echo Ist Python installiert und im PATH? Test: python --version
pause
exit /b 1
