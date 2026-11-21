#!/usr/bin/env zsh
# ==============================================================================
# Eagles Wing ML Recommendation Lab - Safe Project Context Exporter Launcher
# ==============================================================================
# Resolves project root safely, detects virtualenv or system Python, and runs
# the context exporter to produce a sanitized, privacy-conscious report.
# ==============================================================================

set -e

# 1. Resolve project root based on the script's own physical location
PROJECT_ROOT="${0:A:h}"

# 2. Verify tools/context_exporter.py exists
EXPORTER_SCRIPT="${PROJECT_ROOT}/tools/context_exporter.py"
if [[ ! -f "${EXPORTER_SCRIPT}" ]]; then
    echo "Error: Exporter helper not found at ${EXPORTER_SCRIPT}" >&2
    exit 1
fi

# 3. Locate appropriate Python interpreter (prefer project .venv)
PYTHON_BIN=""
if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "Error: No Python interpreter found. Please install Python 3 or create a virtual environment." >&2
    exit 1
fi

# 4. Execute context_exporter.py with project root and passed arguments
exec "${PYTHON_BIN}" "${EXPORTER_SCRIPT}" --project-root "${PROJECT_ROOT}" "$@"
