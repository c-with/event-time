# 快速部署顺序

1. `./scripts/init-env.sh`
2. `./deploy.sh build`
3. `./deploy.sh setup-db`
4. `./deploy.sh init-db`
5. 创建一致性 SQLite 备份：`python3 scripts/sqlite_backup.py <现有activity.sqlite3路径> migration-source/activity.sqlite3`
6. `./deploy.sh migrate`
7. `./deploy.sh start`
8. `./deploy.sh status`
9. 按 `ACCEPTANCE-CHECKLIST.md` 验收；不要提前切换 NPM 正式入口。
10. `./deploy.sh backup` 并执行 `./deploy.sh restore-test <dump路径>`。

原 8600/SQLite 进程在整个验收期保持不变。若 `setup-db`、迁移或恢复任一步失败，停止后续步骤并保留错误输出，不要清空目标数据库重试。
