@echo off
chcp 65001 >nul
title VoxStudio (che do kiem tra loi)
cd /d "%~dp0"
set "HF_HOME=%~dp0cache\hf"
set "MODELSCOPE_CACHE=%~dp0cache\modelscope"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HF_HUB_OFFLINE=1"
if not exist ".venv\Scripts\python.exe" (
  echo Chua cai dat. Hay chay install.bat truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
pause
