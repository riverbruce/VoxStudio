@echo off
chcp 65001 >nul
title VoxStudio - Phat hanh ban cap nhat
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\publish.py
echo.
pause
