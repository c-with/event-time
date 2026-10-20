#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/logs"
LINE="15 3 * * * cd '$ROOT' && ./scripts/backup.sh >> '$ROOT/logs/backup-cron.log' 2>&1"
( crontab -l 2>/dev/null | grep -vF "$ROOT/scripts/backup.sh" || true; echo "$LINE" ) | crontab -
echo "Installed daily 03:15 backup cron for $ROOT"
echo "Ensure BACKUP_DIR has enough space; a separate disk/off-host copy is recommended."
