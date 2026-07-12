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

# ImageMagick
if command -v convert &>/dev/null; then
    echo "[OK] ImageMagick $(convert -version | head -1) already installed"
else
    echo "[install] Installing ImageMagick..."
    sudo apt-get update -qq
    sudo apt-get install -y imagemagick
    echo "[OK] ImageMagick installed"
fi

echo ""
echo "=== Setup Complete ==="
echo "Next: run bin\\setup_sendto.bat on the Windows side"
