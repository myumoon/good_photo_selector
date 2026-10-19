#!/bin/bash
# Install dependencies for GootPhotoSelector (WSL / Ubuntu / Debian)

set -euo pipefail

echo "=== GootPhotoSelector Setup ==="
echo ""

# exiftool
if command -v exiftool &>/dev/null; then
    echo "[OK] exiftool $(exiftool -ver) already installed"
else
    echo "[install] Installing exiftool..."
    sudo apt-get update -qq
    sudo apt-get install -y libimage-exiftool-perl
    echo "[OK] exiftool $(exiftool -ver) installed"
fi

# Pillow
if python3 -c "from PIL import Image" &>/dev/null; then
    echo "[OK] Pillow already installed"
else
    echo "[install] Installing Pillow..."
    sudo apt-get update -qq
    sudo apt-get install -y python3-pil
    echo "[OK] Pillow installed"
fi

echo ""
echo "=== Setup Complete ==="
echo "Next: run bin\\setup_sendto.bat on the Windows side"
