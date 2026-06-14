@echo off
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0Working Ver.py"
    exit /b 0
)

where pyw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pyw.exe -3 "%~dp0Working Ver.py"
    exit /b 0
)

echo Could not find pythonw.exe or pyw.exe.
echo Install Python, then run:
echo   python -m pip install -r requirements.txt
pause
