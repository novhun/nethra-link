@echo off
title NethraLink - Windows Setup

echo 🚀 Starting NethraLink Setup...

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found. Please install Python 3.10+ from python.org and ensure 'Add to PATH' is checked.
    pause
    exit /b
)

:: 2. Create Virtual Environment
echo 📦 Creating virtual environment...
python -m venv .venv

:: 3. Activate and Install Dependencies
echo 📥 Installing dependencies...
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ✅ Setup Complete!
echo -------------------------------------------------------
echo To start the app:
echo   .venv\Scripts\activate
echo   python main.py
echo -------------------------------------------------------
echo 🎥 VIRTUAL CAMERA DRIVERS (Required for VCam feature):
echo   - Unity Video Capture (Windows): https://github.com/mrayy/UnityVideoCapture
echo   - OBS Virtual Camera: Included with OBS Studio
echo -------------------------------------------------------
pause
