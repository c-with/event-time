# Event Time · 活动执行工作台 V0.4.1

本仓库以 V0.4.1 作为唯一当前开发主线。V0.3 及更早版本只保留在 Git 历史中，不再作为当前产品说明。

## 当前交付状态

这是 **Docker + PostgreSQL 部署候选版本**，不是已通过生产验收的版本。源码已入库；开发机报告记录了单元测试 4/4 通过及 Python、JavaScript、Shell、Compose YAML 静态检查通过。Docker 镜像构建、真实 PostgreSQL 集成、旧数据迁移、真实浏览器、多设备并发、手机图片格式和备份恢复仍须在 WS 独立测试环境验证。

**不要直接覆盖当前运行于 8600 的 SQLite 服务。** 新版默认绑定 `127.0.0.1:8601`，验收期间旧服务和正式反向代理保持不变。

## 业务主线

项目是上层业务对象，关联零到多个活动场次、执行工作包、物料需求、任务、时间节点、文件和变更历史。纯物料项目可以没有活动场次。项目与日历、近期执行、检索应读取同一套业务数据。

## 仓库内容

- `app.py` / `models.py`：Flask 应用、业务 API 和 SQLAlchemy 关系模型。
- `static/`：日历台账、项目工作台和资源库前端。
- `compose.yaml` / `Dockerfile`：应用容器配置，连接现有 `postgresql` 容器及 `infra-db` 网络。
- `scripts/import_v03_json.py`：旧版 JSON 台账导入工具（支持预演）；附件文件需单独迁移和核对。
- `scripts/backup.sh`、`scripts/restore-test.sh`、`scripts/sqlite_backup.py`：备份及恢复相关工具。
- `tests/`：当前自动化测试。
- `docs/WORKBENCH-V0.4.1-REQUIREMENTS-BASELINE.md`：冻结的业务需求基线。
- `ACCEPTANCE-CHECKLIST.md`：独立测试环境验收清单。

## 首次启动（独立测试环境）

前置条件：WS 已安装 Docker Engine/Compose；现有 PostgreSQL 容器名为 `postgresql`；外部 Docker 网络 `infra-db` 已存在。

```bash
./scripts/init-env.sh
./deploy.sh build
./deploy.sh setup-db
./deploy.sh init-db
./deploy.sh start
./deploy.sh status
```

首次初始化前，必须确认目标是独立数据库 `activity_workbench`，应用角色为 `activity_workbench_app`。不要将 `.env`、密码、生产数据、上传文件或备份提交到 Git。

## 旧数据迁移边界

当前部署脚本提供的是 `import-v03-json` JSON 导入命令；**没有经过验证的直接 SQLite 到规范化业务模型的一键迁移流程**。如果旧工作台只有 SQLite 数据库，不要直接运行未完成集成验证的旧迁移脚本，也不要对生产库使用覆盖参数。先做 SQLite 一致性备份，再准备并核验 JSON 导出和导入映射；附件必须单独盘点、复制并核对关联。

JSON 导入预演示例：

```bash
./deploy.sh import-v03-json /migration-source/activity.json --dry-run
```

在容器挂载路径、目标库为空、导入数量和字段映射都确认前，不要执行正式导入。

## 检查与验收

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py models.py merge_logic.py scripts/import_v03_json.py scripts/sqlite_backup.py
node --check static/app.js
for f in deploy.sh scripts/*.sh; do bash -n "$f"; done
```

上述静态检查不代替 Docker/PG 集成测试。生产切换前必须完成 `ACCEPTANCE-CHECKLIST.md`，包括数据核对、真实浏览器操作、附件验证、备份恢复和回滚演练。

## 当前版本规则

V0.4.1 是 `main` 的当前主线；V0.3 只作为迁移来源和 Git 历史。业务需求以 `docs/WORKBENCH-V0.4.1-REQUIREMENTS-BASELINE.md` 为准。AI 与对象存储不属于首期运行前置条件。
