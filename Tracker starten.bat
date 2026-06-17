@echo off
REM Startet den FH6 Time-Attack-Tracker (live). Einfach doppelklicken.
REM Bekannte Strecken werden sofort erkannt, neue nach der ersten Runde gelernt.
REM Zeiten landen in lap_times.csv / bestlaps.csv. Beenden mit Strg+C.
cd /d "%~dp0"
py -m fh6tracker.tracker
echo.
echo Beendet. Fenster kann geschlossen werden.
pause
