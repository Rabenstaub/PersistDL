@echo off
rem Signiert PersistDL.exe mit dem in SimplySign Desktop angemeldeten
rem Zertifikat. WICHTIG: SimplySign Desktop muss vorher gestartet und
rem eingeloggt sein (Handy-Bestaetigung), sonst findet signtool kein
rem Zertifikat.
rem
rem Diese Datei einfach in denselben Ordner wie PersistDL.exe legen und
rem doppelklicken.
cd /d "%~dp0"

set SIGNTOOL="C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"

if not exist PersistDL.exe (
    echo FEHLER: PersistDL.exe liegt nicht in diesem Ordner ^(%~dp0^).
    echo Diese .bat-Datei muss neben PersistDL.exe liegen.
    pause
    exit /b 1
)

echo Signiere PersistDL.exe ...
%SIGNTOOL% sign /a /tr http://time.certum.pl /td sha256 /fd sha256 PersistDL.exe
if errorlevel 1 goto fail

echo.
echo Pruefe die Signatur ...
%SIGNTOOL% verify /pa PersistDL.exe
if errorlevel 1 goto fail

echo.
echo FERTIG - PersistDL.exe ist signiert.
pause
exit /b 0

:fail
echo.
echo FEHLER beim Signieren - siehe Meldung oben.
echo Laeuft SimplySign Desktop und bist du dort eingeloggt/verbunden?
pause
exit /b 1
