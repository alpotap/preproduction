@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Starts local_web.py if not running; if running on port 8000, asks whether to restart.
cd /d "%~dp0"

REM Load Azure AI Foundry environment variables from user profile
for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_API_KEY 2^>nul') do set "AZURE_AI_FOUNDRY_API_KEY=%%B"
for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_ENDPOINT 2^>nul') do set "AZURE_AI_FOUNDRY_ENDPOINT=%%B"
for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_API_VERSION 2^>nul') do set "AZURE_AI_FOUNDRY_API_VERSION=%%B"
for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_MODEL_NAME 2^>nul') do set "AZURE_AI_FOUNDRY_MODEL_NAME=%%B"
for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_PROFILE_IDS 2^>nul') do set "AZURE_AI_FOUNDRY_PROFILE_IDS=%%B"

if defined AZURE_AI_FOUNDRY_PROFILE_IDS (
	for %%P in (%AZURE_AI_FOUNDRY_PROFILE_IDS:,= %) do (
		set "FOUND_PROFILE=%%~P"
		if defined FOUND_PROFILE (
			for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_!FOUND_PROFILE!_API_KEY 2^>nul') do set "AZURE_AI_FOUNDRY_!FOUND_PROFILE!_API_KEY=%%B"
			for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_!FOUND_PROFILE!_ENDPOINT 2^>nul') do set "AZURE_AI_FOUNDRY_!FOUND_PROFILE!_ENDPOINT=%%B"
			for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_!FOUND_PROFILE!_API_VERSION 2^>nul') do set "AZURE_AI_FOUNDRY_!FOUND_PROFILE!_API_VERSION=%%B"
			for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\Environment" /v AZURE_AI_FOUNDRY_!FOUND_PROFILE!_MODEL_NAME 2^>nul') do set "AZURE_AI_FOUNDRY_!FOUND_PROFILE!_MODEL_NAME=%%B"
		)
	)
)

set "PORT=8000"
set "PIDS="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
	set "PIDS=!PIDS! %%P"
)

if defined PIDS (
	echo Detected an existing process listening on port %PORT%:
	for %%P in (!PIDS!) do (
		if not "%%P"=="" (
			tasklist /FI "PID eq %%P" | findstr /I /V "Image Name" >nul
			echo   PID %%P
		)
	)
	choice /C YN /N /M "Kill and restart web server? [Y/N]: "
	if errorlevel 2 (
		echo Keeping existing server. Exiting.
		exit /b 0
	)

	for %%P in (!PIDS!) do (
		if not "%%P"=="" taskkill /PID %%P /F >nul 2>nul
	)
	timeout /t 1 >nul
)

echo Starting local web server at http://127.0.0.1:%PORT%
python local_web.py

if errorlevel 1 (
	echo.
	echo local_web.py exited with an error.
	pause
)
