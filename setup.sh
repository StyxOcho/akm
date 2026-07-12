#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Setup script untuk menjalankan ab.py di VPS Ubuntu
# Usage: chmod +x setup_vps.sh && ./setup_vps.sh
# ═══════════════════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════════════"
echo "  ABCK Token Generator - Ubuntu VPS Setup"
echo "══════════════════════════════════════════════"
echo ""

# Update system
echo "[1/5] Updating system packages..."
sudo apt-get update -y

# Install Chrome
echo "[2/5] Installing Google Chrome..."
if ! command -v google-chrome &> /dev/null; then
    wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y /tmp/google-chrome.deb || sudo apt-get install -f -y
    rm -f /tmp/google-chrome.deb
    echo "  ✔ Google Chrome installed"
else
    echo "  ✔ Google Chrome already installed"
fi

# Install Xvfb (virtual display)
echo "[3/5] Installing Xvfb (virtual display)..."
sudo apt-get install -y xvfb

# Install Python dependencies
echo "[4/5] Installing Python dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv

# Create virtual environment and install packages
echo "[5/5] Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install undetected-chromedriver requests xvfbwrapper

echo ""
echo "══════════════════════════════════════════════"
echo "  ✔ Setup selesai!"
echo "══════════════════════════════════════════════"
echo ""
echo "Cara menjalankan:"
echo "  source venv/bin/activate"
echo "  python3 ab.py"
echo ""
echo "Opsi tambahan:"
echo "  python3 ab.py --hidden        # Browser background"
echo "  python3 ab.py --save-file     # Simpan ke abck.txt"
echo "  python3 ab.py --no-server     # Tanpa server"
echo "  python3 ab.py 50              # Generate 50 token"
echo ""
echo "Jalankan di background dengan screen/tmux:"
echo "  screen -S abck"
echo "  source venv/bin/activate && python3 ab.py"
echo "  # Ctrl+A, D untuk detach"
echo ""
