@echo off
cd /d "%~dp0"
python scripts\junkies_sammeln.py
python scripts\junkies_webseite.py
echo.
echo Fertig. Seite: junkies\webseite\index.html
pause
