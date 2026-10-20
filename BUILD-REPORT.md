# V0.3.0 构建与静态验证报告

构建目标：活动执行工作台 Docker + PostgreSQL 部署候选包。

## 已执行的检查

- `python3 -m unittest discover -s tests -v`：4/4 PASS。覆盖不同字段合并、同字段冲突保留服务端值、并发新增、冲突字段之外的修改仍可保存。
- Python `py_compile`：app.py、merge_logic.py、migrate_sqlite_to_pg.py、scripts/sqlite_backup.py 均通过。
- Node `--check`：从 static/index.html 提取的 inline JavaScript 语法检查通过。
- `bash -n`：deploy.sh 和所有 shell 脚本通过。
- PyYAML：compose.yaml 成功解析；确认应用只定义一个服务，PostgreSQL 网络为 external `infra-db`。
- sample-data.json：JSON 可解析；包含 22 活动、18 物料、3 项基础资料、2 条初始化变更，以及新增的空 suppliers/workPackages/venues 集合。
- SQLite Backup API：用临时 SQLite fixture 实测创建一致性备份，`PRAGMA integrity_check=ok`，SHA-256 输出正常。

## 未执行／必须在 WS 验收的项目

- 本执行环境没有 Docker CLI，也没有到 WS 的 PostgreSQL 连接，因此**没有构建真实 Docker image、执行 PostgreSQL DDL、跑迁移集成测试或启动服务**。
- 未完成真实浏览器多设备测试、HEIC 实际解码验收、上传大文件代理测试、NPM HTTPS 分享链接验证及 PostgreSQL 恢复演练。
- 不可把静态测试 PASS 当作生产部署 PASS。必须按 README 的 build → setup-db → init-db → migrate → start 顺序在 WS 的独立测试入口执行，并通过 ACCEPTANCE-CHECKLIST.md。

## 安全边界

- 压缩包不包含 `.env`、数据库文件、生产数据或密码。
- 新应用端口默认仅绑定 `127.0.0.1:8601`，不会覆盖现有 8600 服务。
- 本包不会自动修改 Nginx Proxy Manager 正式入口。
