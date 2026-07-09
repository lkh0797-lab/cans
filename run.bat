@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create 32-bit venv first:
  echo   "C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
echo Exit %ERRORLEVEL%
if "%1"=="nopause" exit /b %ERRORLEVEL%
pause
exit /b %ERRORLEVEL%
