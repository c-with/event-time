#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 2; }
set -a; source ./.env; set +a
DUMP="${1:-}"
[[ -n "$DUMP" && -f "$DUMP" ]] || { echo "Usage: $0 /path/to/activity-YYYYMMDD-HHMMSS.dump" >&2; exit 2; }
TEST_DB="activity_workbench_restore_test_$(date +%s)"
cleanup(){ docker exec postgresql psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$TEST_DB\" WITH (FORCE);" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker exec postgresql psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TEST_DB\" OWNER activity_workbench_app;"
docker exec -i -e PGPASSWORD="$DB_PASSWORD" postgresql pg_restore --list < "$DUMP" >/dev/null
docker exec -i -e PGPASSWORD="$DB_PASSWORD" postgresql pg_restore -h /var/run/postgresql -U activity_workbench_app -d "$TEST_DB" --no-owner --no-privileges < "$DUMP"
TABLES="$(docker exec -e PGPASSWORD="$DB_PASSWORD" postgresql psql -h /var/run/postgresql -U activity_workbench_app -d "$TEST_DB" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('projects','event_sessions','work_packages','requirement_items','tasks','documents','audit_log');")"
[[ "$TABLES" == "7" ]] || { echo "FAIL: restored core tables=$TABLES, expected 7" >&2; exit 1; }
PROJECTS="$(docker exec -e PGPASSWORD="$DB_PASSWORD" postgresql psql -h /var/run/postgresql -U activity_workbench_app -d "$TEST_DB" -Atc 'SELECT count(*) FROM projects;')"
echo "PASS: restore test DB $TEST_DB has 7 core tables and $PROJECTS projects; temporary DB will be dropped."
