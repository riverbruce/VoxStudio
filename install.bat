@echo off
chcp 65001 >nul
title VoxStudio - Cai dat / Sua loi
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
