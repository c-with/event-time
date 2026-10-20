#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
# Load deployment settings for host-side commands (not only Docker Compose).
if [[ -f .env ]]; then
  set -a
  source ./.env
  set +a
fi
cmd="${1:-help}"
case "$cmd" in
  build)
    docker compose build event-time
    ;;
  setup-db)
    ./scripts/setup-postgres.sh
    ;;
  init-db)
    docker compose run --rm --no-deps --entrypoint python event-time app.py init-db
    ;;
  seed-demo)
    echo "警告：此操作会在空数据库写入演示项目，不应在正式数据中运行。"
    read -r -p "输入 SEED-DEMO 确认：" confirm
    [[ "$confirm" == "SEED-DEMO" ]] || { echo "已取消"; exit 2; }
    docker compose run --rm --no-deps --entrypoint python event-time app.py seed-demo
    ;;
  import-v03-json)
    shift || true
    [[ -n "${1:-}" ]] || { echo "用法：./deploy.sh import-v03-json /migration-source/activity.json [--allow-nonempty]" >&2; exit 2; }
    docker compose run --rm --no-deps --entrypoint python event-time scripts/import_v03_json.py "$@"
    ;;
  start)
    docker compose up -d --build event-time
    ;;
  status)
    docker compose ps
    curl -fsS "http://127.0.0.1:${HOST_PORT:-8601}/health"
    echo
    ;;
  logs)
    docker compose logs --tail=200 -f event-time
    ;;
  backup)
    ./scripts/backup.sh
    ;;
  restore-test)
    shift || true
    ./scripts/restore-test.sh "${1:-}"
    ;;
  stop)
    docker compose stop event-time
    ;;
  help|--help|-h)
    cat <<'EOF'
Event Time / 活动执行工作台 V0.4.1

Commands:
  ./scripts/init-env.sh                     Generate a private .env and random credentials
  ./deploy.sh build                          Build application image
  ./deploy.sh setup-db                       Create/reuse the dedicated PostgreSQL role/database
  ./deploy.sh init-db                        Create normalized schema and shared login; no demo data
  ./deploy.sh import-v03-json <file>         Import a manually exported V0.3 JSON file; non-destructive
  ./deploy.sh seed-demo                      Explicitly seed demo records (empty DB only)
  ./deploy.sh start                          Start isolated app on 127.0.0.1:8601
  ./deploy.sh status                         Show container and health status
  ./deploy.sh logs                           Follow app logs
  ./deploy.sh backup                         Back up PostgreSQL and uploaded files
  ./deploy.sh restore-test <dump>             Restore into a temporary database and verify tables
  ./deploy.sh stop                           Stop only this app

Recommended order: init-env -> build -> setup-db -> init-db -> start -> acceptance tests.
Keep the existing 8600/SQLite service and reverse proxy unchanged until all acceptance gates pass.
EOF
    ;;
  *) echo "Unknown command: $cmd" >&2; exit 2 ;;
esac
