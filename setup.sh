#!/bin/bash

# NethraLink - Mac/Linux Setup Script

echo "🚀 Starting NethraLink Setup..."

# 1. Check Python
if ! command -v python3 &> /dev/null
then
    echo "❌ Python3 not found. Please install it from python.org"
    exit 1
fi

# 2. Create Virtual Environment
echo "📦 Creating virtual environment..."
python3 -m venv .venv

# 3. Activate and Install Dependencies
echo "📥 Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Check for ADB
if ! command -v adb &> /dev/null
then
    echo "⚠️ ADB not found in PATH."
    echo "💡 Recommendation: Install via Homebrew: 'brew install --cask android-platform-tools'"
fi

echo ""
echo "✅ Setup Complete!"
echo "-------------------------------------------------------"
echo "To start the app:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo "-------------------------------------------------------"
echo "🎥 VIRTUAL CAMERA DRIVERS (Required for VCam feature):"
echo "  - Unity Video Capture (Mac): https://github.com/mrayy/UnityVideoCapture"
echo "  - OBS Virtual Camera: Included with OBS Studio"
echo "-------------------------------------------------------"
