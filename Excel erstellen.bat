@echo off
REM Erstellt FH6_Rundenzeiten.xlsx aus den bisher gefahrenen Zeiten.
cd /d "%~dp0"
py -m fh6tracker.excel_export
echo.
pause
