@echo off
set ROOT_DIR=%~dp0
cd /d %ROOT_DIR%
python src\run_and_email.py --config config\settings.json --out-dir output
