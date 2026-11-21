#!/usr/bin/env zsh
# ==============================================================================
# Eagles Wing ML Recommendation Lab - Application Launcher
# ==============================================================================
set -e

PROJECT_ROOT="${0:A:h}"
cd "${PROJECT_ROOT}"

echo "=================================================="
echo "🦅 Starting Eagles Wing ML Recommendation Service"
echo "=================================================="
echo "Project Directory: ${PROJECT_ROOT}"

# 1. Verify or initialize virtual environment
VENV_DIR="${PROJECT_ROOT}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "⚠️  Virtual environment not found at ${VENV_DIR}"
    echo "Creating virtual environment..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv "${VENV_DIR}"
        echo "Installing requirements from requirements.txt..."
        "${VENV_DIR}/bin/pip" install --upgrade pip
        "${VENV_DIR}/bin/pip" install -r "${PROJECT_ROOT}/requirements.txt"
    else
        echo "❌ Error: python3 is not installed or not in PATH." >&2
        exit 1
    fi
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# 2. Verify Streamlit is installed
if ! command -v streamlit >/dev/null 2>&1; then
    echo "⚠️  Streamlit not found in virtualenv. Installing dependencies..."
    pip install --upgrade pip
    pip install -r "${PROJECT_ROOT}/requirements.txt"
fi

# 3. Check for recommendation artifacts
if [[ ! -f "${PROJECT_ROOT}/artifacts/embeddings.npy" || ! -f "${PROJECT_ROOT}/artifacts/manifest.json" || ! -f "${PROJECT_ROOT}/artifacts/catalog.json" ]]; then
    echo "⚠️  Model artifacts missing in ${PROJECT_ROOT}/artifacts!"
    if [[ -f "${PROJECT_ROOT}/YoutubeLinksWithInfo - Sheet1.csv" ]]; then
        echo "Building index from local CSV..."
        python "${PROJECT_ROOT}/build_index.py" --csv "${PROJECT_ROOT}/YoutubeLinksWithInfo - Sheet1.csv" --device cpu
    else
        echo "❌ Error: Required index artifacts missing. Please run build_index.py first." >&2
        exit 1
    fi
fi

echo "🚀 Launching Streamlit server on http://localhost:8501 ..."
exec streamlit run "${PROJECT_ROOT}/server.py" "$@"
