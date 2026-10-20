#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ ! -e .env ]] || { echo ".env 已存在；为避免覆盖凭证，脚本退出。" >&2; exit 2; }
command -v openssl >/dev/null || { echo "需要 openssl 生成随机凭证" >&2; exit 2; }
DB_PASSWORD="$(openssl rand -hex 32)"
SHARED_PASSWORD="$(openssl rand -hex 24)"
SESSION_SECRET="$(openssl rand -hex 32)"
cat > .env <<EOF
DB_PASSWORD=$DB_PASSWORD
SHARED_USERNAME=activity
SHARED_DISPLAY_NAME=活动工作台共享账号
SHARED_PASSWORD=$SHARED_PASSWORD
SESSION_SECRET=$SESSION_SECRET
HOST_PORT=8601
COOKIE_SECURE=1
APP_UID=$(id -u)
APP_GID=$(id -g)
BACKUP_DIR=./backups
EOF
chmod 600 .env
mkdir -p data migration-source backups logs
chmod 700 data backups migration-source logs
cat <<EOF
已创建 .env（权限 600）。
共享账号：activity
共享密码：$SHARED_PASSWORD
请立即把共享密码保存到安全位置；该密码只在本次显示。
DB_PASSWORD 与 SESSION_SECRET 已安全写入 .env，不在此显示。
EOF
