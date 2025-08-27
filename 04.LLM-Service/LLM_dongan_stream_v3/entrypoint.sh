#!/usr/bin/env bash
set -euo pipefail

# 예: DB 마이그레이션, 정적파일 빌드 등
# flask db upgrade || true

echo "Starting Gunicorn..."
exec "$@"
