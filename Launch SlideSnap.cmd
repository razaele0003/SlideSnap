@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\SlideSnap\SlideSnap.exe" (
    start "" "%~dp0dist\SlideSnap\SlideSnap.exe" %*
    exit /b
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" %*
    exit /b
)
if exist "%~dp0..\.venv-slidesnap\Scripts\pythonw.exe" (
    start "" "%~dp0..\.venv-slidesnap\Scripts\pythonw.exe" "%~dp0main.py" %*
    exit /b
)
echo Run install.ps1 once to install SlideSnap, then open this launcher again.
pause
