@echo off
setlocal
cd /d "%~dp0"
title Clipbot

where python >nul 2>nul
if errorlevel 1 (
  echo Python fehlt. Installiere es in der PowerShell mit:
  echo     winget install Python.Python.3.12
  echo Danach dieses Fenster schliessen und start.bat erneut doppelklicken.
  pause
  exit /b 1
)

if not exist venv\Scripts\python.exe (
  echo Erster Start: Clipbot wird eingerichtet. Das dauert ein paar Minuten ...
  python -m venv venv
  if errorlevel 1 (
    echo Einrichtung fehlgeschlagen.
    pause
    exit /b 1
  )
)

call venv\Scripts\activate.bat

if not exist venv\.installed (
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installation der Pakete fehlgeschlagen. Ist das Internet an?
    pause
    exit /b 1
  )
  echo ok> venv\.installed
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg fehlt. Versuche die Installation ...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  echo Falls ffmpeg danach weiter fehlt: dieses Fenster schliessen und start.bat neu starten.
)

echo.
echo Clipbot startet. Die Seite oeffnet sich im Browser. Dieses Fenster offen lassen!
python -m clipbot ui
pause
