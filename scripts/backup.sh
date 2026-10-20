#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 2; }
set -a; source ./.env; set +a
BACKUP_DIR="${BACKUP_DIR:-/srv/backups/activity-workbench}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"
TMP_DB="$BACKUP_DIR/daily/.activity-${STAMP}.dump.tmp"
TMP_DATA="$BACKUP_DIR/daily/.data-${STAMP}.tar.gz.tmp"
trap 'rm -f "$TMP_DB" "$TMP_DATA"' EXIT
# Dump through the existing PostgreSQL container; do not start a second database.
docker exec -e PGPASSWORD="$DB_PASSWORD" postgresql pg_dump -h /var/run/postgresql -U activity_workbench_app -d activity_workbench -Fc > "$TMP_DB"
docker exec -i -e PGPASSWORD="$DB_PASSWORD" postgresql pg_restore --list < "$TMP_DB" >/dev/null
tar -czf "$TMP_DATA" -C "$ROOT" data
mv "$TMP_DB" "$BACKUP_DIR/daily/activity-${STAMP}.dump"
mv "$TMP_DATA" "$BACKUP_DIR/daily/data-${STAMP}.tar.gz"
(
  cd "$BACKUP_DIR/daily"
  sha256sum "activity-${STAMP}.dump" "data-${STAMP}.tar.gz" > "SHA256-${STAMP}.txt"
)
if [[ "$(date +%u)" == "7" ]]; then
  cp "$BACKUP_DIR/daily/activity-${STAMP}.dump" "$BACKUP_DIR/weekly/"
  cp "$BACKUP_DIR/daily/data-${STAMP}.tar.gz" "$BACKUP_DIR/weekly/"
  (cd "$BACKUP_DIR/weekly" && sha256sum "activity-${STAMP}.dump" "data-${STAMP}.tar.gz" > "SHA256-${STAMP}.txt")
fi
# Keep at least 7 daily DB dumps + 7 daily file archives and 4 weekly copies of each.
# `|| true` guards each cleanup pipeline: ls exits non-zero when a glob has no match
# (e.g. empty weekly/ dir), which under `set -euo pipefail` would abort the script
# after the backup was already written successfully.
ls -1t "$BACKUP_DIR"/daily/activity-*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f || true
ls -1t "$BACKUP_DIR"/daily/data-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f || true
ls -1t "$BACKUP_DIR"/daily/SHA256-*.txt 2>/dev/null | tail -n +8 | xargs -r rm -f || true
ls -1t "$BACKUP_DIR"/weekly/activity-*.dump 2>/dev/null | tail -n +5 | xargs -r rm -f || true
ls -1t "$BACKUP_DIR"/weekly/data-*.tar.gz 2>/dev/null | tail -n +5 | xargs -r rm -f || true
ls -1t "$BACKUP_DIR"/weekly/SHA256-*.txt 2>/dev/null | tail -n +5 | xargs -r rm -f || true
trap - EXIT
echo "PASS backup created: $BACKUP_DIR/daily/activity-${STAMP}.dump and data-${STAMP}.tar.gz"
