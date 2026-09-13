@echo off
rem Baut PersistDL.exe (PyInstaller, Onefile). Ergebnis: dist\PersistDL.exe
rem + dist\lang\ (Sprachdateien werden daneben kopiert, nicht eingebettet -
rem so bleiben sie fuer jeden weiter selbst anpassbar/erweiterbar).
cd /d "%~dp0"

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installiere PyInstaller - einmalig ...
    python -m pip install pyinstaller
    if errorlevel 1 goto fail
)

echo Baue PersistDL.exe ...
python -m PyInstaller --noconfirm PersistDL.spec
if errorlevel 1 goto fail

echo Kopiere lang\-Ordner neben die exe ...
xcopy /E /I /Y lang dist\lang >nul

echo.
echo Fertig: dist\PersistDL.exe (+ dist\lang\)
echo Vor der Weitergabe: mit SimplySign signieren (signtool sign ...).
pause
exit /b 0

:fail
echo.
echo FEHLER beim Bauen - siehe Ausgabe oben.
pause
exit /b 1
