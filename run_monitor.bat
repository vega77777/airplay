@echo off
cd /d "%~dp0"
python monitor.py >> monitor.log 2>&1
