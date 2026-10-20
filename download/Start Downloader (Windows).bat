@echo off
rem Double-click this file in Windows to open the downloader.
rem It runs the app inside Ubuntu (WSL), where bbftp is installed.
wsl --cd "%~dp0" python3 download_gui.py
if errorlevel 1 (
  echo.
  echo The downloader could not start. See "Using it from Windows" in README.md.
  pause
)
