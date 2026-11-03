#!/usr/bin/env bash
# Run the dashboard on your Mac with a FAKE radio (nothing is transmitted).
#   ./run_mock.sh     then open http://localhost:8080
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
# Mock hits go to a scratch file so the real codes.json stays clean.
ULIGHT_MOCK=1 ULIGHT_CODES="${ULIGHT_CODES:-/tmp/ulight-mock-codes.json}" exec python -m web.app
