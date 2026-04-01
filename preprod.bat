@echo off
REM Batch file to run the document processing wizard in CMD window
cd /d "%~dp0"
python process.py
pause
