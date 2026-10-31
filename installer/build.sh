#!/bin/sh
# Đóng gói VoxStudio-Setup.exe (chạy trên Linux có makensis)
set -e
cd "$(dirname "$0")"
rm -rf payload && mkdir payload
for f in app scripts assets main.py version.json requirements.txt install.ps1 install.bat run.bat VoxStudio.vbs HUONG_DAN.md .gitignore; do
  cp -r "../$f" payload/
done
find payload -name __pycache__ -prune -exec rm -rf {} +
rm -f payload/scripts/publish.py
mkdir -p ../dist
V=$(python3 -c "import json;print(json.load(open('../version.json'))['version'])")
makensis -V2 -DVERSION="$V" VoxStudio.nsi
rm -rf payload
ls -la ../dist
