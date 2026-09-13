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

rem Exe kann direkt neben dieser .bat liegen (entpacktes ZIP) oder im
rem dist\-Unterordner (Ergebnis von Build-EXE.bat) - beides pruefen.
if exist PersistDL.exe (
    set TARGET=PersistDL.exe
) else if exist dist\PersistDL.exe (
    set TARGET=dist\PersistDL.exe
) else (
    echo FEHLER: PersistDL.exe wurde weder in diesem Ordner
    echo ^(%~dp0^) noch in dessen dist\-Unterordner gefunden.
    pause
    exit /b 1
)

echo Signiere %TARGET% ...
rem WICHTIG: /n statt /a - "/a" (automatische Auswahl) hatte bei Christian
rem faelschlich ein technisches SimplySign-internes "trust_..."-Zertifikat
rem erwischt statt des echten Certum-Code-Signing-Zertifikats. /n waehlt
rem gezielt ueber den Zertifikatsnamen.
%SIGNTOOL% sign /n "Christian Diezinger" /tr http://time.certum.pl /td sha256 /fd sha256 %TARGET%
if errorlevel 1 goto fail

echo.
echo Pruefe die Signatur ...
%SIGNTOOL% verify /pa %TARGET%
if errorlevel 1 goto fail

echo.
echo FERTIG - %TARGET% ist signiert.
pause
exit /b 0

:fail
echo.
echo FEHLER beim Signieren - siehe Meldung oben.
echo Laeuft SimplySign Desktop und bist du dort eingeloggt/verbunden?
pause
exit /b 1
