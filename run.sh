#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export DASHBOARD_MIN_INTERVAL="${DASHBOARD_MIN_INTERVAL:-0.8}"
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
