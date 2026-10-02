@echo off
rem Taku - double click to start (needs Python 3.10+ and pip install -r requirements.txt)
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw src\app.py
  exit /b 0
)
python src\app.py
pause
