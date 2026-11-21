#!/usr/bin/env zsh
# ==============================================================================
# Eagles Wing ML Recommendation Lab - macOS Double-Clickable Launcher (.command)
# ==============================================================================

# Ensure working directory is the project directory when launched via Finder
PROJECT_ROOT="${0:A:h}"
cd "${PROJECT_ROOT}"

# Keep Terminal window open if an error occurs so the message can be read
trap 'EXIT_CODE=$?; if [ $EXIT_CODE -ne 0 ]; then echo ""; echo "❌ Process exited with error code $EXIT_CODE. Press any key to close..."; read -k 1 -s; fi' EXIT

# Launch the primary zsh startup script
"${PROJECT_ROOT}/start.zsh" "$@"
