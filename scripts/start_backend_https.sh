#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${HOME}/.office-addin-dev-certs"

cd "${ROOT_DIR}"

if [[ ! -f "${CERT_DIR}/localhost.crt" || ! -f "${CERT_DIR}/localhost.key" ]]; then
  echo "Office add-in dev certificates were not found."
  echo "Run this first: cd frontend && npm start"
  exit 1
fi

venv/bin/uvicorn backend.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000 \
  --ssl-certfile "${CERT_DIR}/localhost.crt" \
  --ssl-keyfile "${CERT_DIR}/localhost.key"
