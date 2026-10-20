#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo "缺少 .env。请先运行 ./scripts/init-env.sh" >&2; exit 2; }
set -a; source ./.env; set +a
: "${DB_PASSWORD:?请在 .env 设置 DB_PASSWORD}"
: "${SHARED_PASSWORD:?请在 .env 设置 SHARED_PASSWORD}"
[[ ${#SHARED_PASSWORD} -ge 14 ]] || { echo "SHARED_PASSWORD 至少14位" >&2; exit 2; }
docker inspect postgresql >/dev/null 2>&1 || { echo "找不到现有容器 postgresql；本项目不会另建 PostgreSQL。" >&2; exit 2; }
docker inspect -f '{{.State.Running}}' postgresql | grep -qx true || { echo "postgresql 容器未运行" >&2; exit 2; }
docker network inspect infra-db >/dev/null 2>&1 || { echo "找不到外部网络 infra-db" >&2; exit 2; }
docker exec -i -e AWB_DB_PASSWORD="$DB_PASSWORD" postgresql psql -U postgres -d postgres -v ON_ERROR_STOP=1 -v app_password="$DB_PASSWORD" <<'SQL'
DO $do$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='activity_workbench_app') THEN
    CREATE ROLE activity_workbench_app LOGIN;
  END IF;
END $do$;
ALTER ROLE activity_workbench_app WITH LOGIN PASSWORD :'app_password';
SELECT format('CREATE DATABASE %I OWNER %I', 'activity_workbench', 'activity_workbench_app')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='activity_workbench') \gexec
ALTER DATABASE activity_workbench OWNER TO activity_workbench_app;
GRANT CONNECT, TEMPORARY ON DATABASE activity_workbench TO activity_workbench_app;
SQL
echo "PASS: 已准备独立 activity_workbench 数据库角色；没有触碰其他业务数据库。"
