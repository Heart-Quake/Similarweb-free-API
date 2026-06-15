#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

PORT="${PORT:-8501}"
FILE_WATCHER_TYPE="${STREAMLIT_FILE_WATCHER_TYPE:-none}"

# Lancement robuste: module Python explicite + watcher désactivé pour éviter les déconnexions.
exec python3 -m streamlit run "$APP_DIR/streamlit_app.py" \
  --server.port "$PORT" \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.fileWatcherType "$FILE_WATCHER_TYPE" \
  --server.runOnSave false
