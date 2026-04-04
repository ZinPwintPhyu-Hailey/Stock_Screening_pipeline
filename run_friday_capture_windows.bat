@echo off
set ROOT_DIR=%~dp0
cd /d %ROOT_DIR%
python src\run_csp_screen.py --config config\settings.json --out-dir output
