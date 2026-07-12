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

# Folder mode: single directory argument
if [ $# -eq 1 ] && [ -d "$1" ]; then
    echo "Target folder: $1"
    echo ""
    PROMPT="Follow the workflow in CLAUDE.md to select photos in \"$1\". Print progress as \"[N/M] Analyzing DSC_XXXX.NEF...\" before each file and \"[N/M] DSC_XXXX.NEF → accepted/rejected\" after labeling. After processing all files, display \"Selection complete: X accepted / Y rejected\"."
else
    # File mode: one or more specific files
    echo "Target files: $# file(s)"
    for f in "$@"; do
        echo "  $f"
    done
    echo ""
    FILE_LIST=$(printf '"%s" ' "$@")
    PROMPT="Follow the workflow in CLAUDE.md to select the following NEF photos: $FILE_LIST. Skip step 1 (file listing) and process only these specific files. Print progress as \"[N/M] Analyzing DSC_XXXX.NEF...\" before each file and \"[N/M] DSC_XXXX.NEF → accepted/rejected\" after labeling. Display \"Selection complete: X accepted / Y rejected\" when done."
fi

unset ANTHROPIC_API_KEY
claude --dangerously-skip-permissions -p "$PROMPT"

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
