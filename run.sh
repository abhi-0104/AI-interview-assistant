#!/bin/bash
# System Management Service — One-command launcher
# Sets up virtual environment, installs dependencies, and launches the app.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "⚙ System Management Service — Starting up..."
echo ""

# Check for BlackHole
if ! system_profiler SPAudioDataType 2>/dev/null | grep -qi "BlackHole"; then
    echo "⚠️  BlackHole audio driver not detected!"
    echo "   For capturing interviewer's voice, install BlackHole 2ch:"
    echo "   brew install blackhole-2ch"
    echo "   Then see setup_audio.md for configuration."
    echo ""
    echo "   (The app will still work with your default microphone)"
    echo ""
fi

# Check for Tesseract (for OCR)
if ! command -v tesseract &> /dev/null; then
    echo "⚠️  Tesseract OCR not detected!"
    echo "   Screen capture OCR will not work without the tesseract binary."
    echo "   Install it with: brew install tesseract"
    echo ""
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# Launch
echo ""
echo "🚀 Initializing System Service..."
echo "   Cmd+M = Toggle monitor pause"
echo "   Drag title bar to move"
echo "   Resize from bottom-right corner"
echo ""
python syssvc.py
