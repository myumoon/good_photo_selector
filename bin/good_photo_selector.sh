#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT"

if [ $# -eq 0 ]; then
    echo "error: no folder or files specified"
    read -r _
    exit 1
fi

echo "=============================="
echo "  GootPhotoSelector"
echo "=============================="

unset ANTHROPIC_API_KEY
python3 src/select_photos.py "$@"

STATUS=$?

echo ""
echo "=============================="
if [ $STATUS -eq 0 ]; then
    echo "  Done"
else
    echo "  Error (code: $STATUS)"
fi
echo "=============================="
echo "Press Enter to close..."
read -r _
