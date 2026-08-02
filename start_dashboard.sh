#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
exec uvicorn app.main:app --host 127.0.0.1 --port "${DASHBOARD_PORT:-8001}" --no-access-log
