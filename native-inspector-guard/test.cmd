@echo off
setlocal
cd /d "%~dp0"
py -3.13 -X utf8 -B tools\run_regression.py
exit /b %errorlevel%
