@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo        LearnSphere AI - Startup
echo ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [1/3] Creating Python virtual environment...
    py -m venv venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        echo Make sure Python is installed and added to PATH.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment already exists.
)

echo [2/3] Installing required packages...
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package installation failed. Check your internet connection.
    pause
    exit /b 1
)

echo [3/3] Starting LearnSphere AI...
echo.
echo Open http://127.0.0.1:5000 in your browser.
echo Press Ctrl+C in this window to stop the server.
echo.
venv\Scripts\python.exe app.py
pause
