#!/bin/sh
set -eu
case "${PINAK_CLOUD_DATA:-/data}" in
  /data) ;;
  *) echo 'Container storage must be mounted at /data' >&2; exit 2 ;;
esac
install -d -m 700 -o 10001 -g 10001 /data
if [ "$#" -eq 0 ]; then
  set -- serve --host 0.0.0.0 --port "${PORT:-8000}"
fi
exec /usr/bin/tini -- /usr/sbin/gosu pinak python -m pinak.mcp_cloud "$@"
