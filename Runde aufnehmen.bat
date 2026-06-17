@echo off
REM Startet den FH6 Trace-Recorder. Einfach doppelklicken.
REM Schreibt ta_trace_<Zeitstempel>.csv (eine Datei je Aufnahme). Strg+C beendet.
cd /d "%~dp0"
py -m fh6tracker.recorder
echo.
echo Fertig. Fenster kann geschlossen werden.
pause
