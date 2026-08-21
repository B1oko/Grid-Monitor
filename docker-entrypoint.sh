#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [ "$(id -u)" = "0" ]; then
  chown -R app:app "$DATA_DIR" 2>/dev/null || true
  exec gosu app "$@"
fi

exec "$@"
