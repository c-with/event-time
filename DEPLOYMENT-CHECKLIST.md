# Event Time V0.4.1 — 测试环境部署顺序

> 仅用于独立测试入口。验收完成前，保持现有 8600/SQLite 服务和正式反向代理不变。

1. 检查 Docker Engine/Compose、`postgresql` 容器和 `infra-db` 网络。
2. 在新工作目录运行 `./scripts/init-env.sh`，安全保存生成的共享密码。
3. 运行 `./deploy.sh build`。
4. 运行 `./deploy.sh setup-db`，核实只操作 `activity_workbench` 和 `activity_workbench_app`。
5. 运行 `./deploy.sh init-db`，确认 schema 初始化成功且没有演示数据。
6. 运行 `./deploy.sh start` 和 `./deploy.sh status`，确认服务只绑定 `127.0.0.1:8601`，健康检查连接 PostgreSQL。
7. 如需导入旧版数据，先完成源数据一致性备份、格式确认和映射抽查。当前脚本支持 V0.3 JSON 导入；必须先验证容器内的迁移文件挂载路径，运行 dry-run 并核对报告。不要把 `./deploy.sh migrate` 或直接 SQLite 迁移当作当前已支持的命令。
8. 按 `ACCEPTANCE-CHECKLIST.md` 完成浏览器、并发、文件、数据库和恢复测试。
9. 运行 `./deploy.sh backup` 并执行恢复演练；备份应复制到独立介质/既有备份体系。
10. 所有门禁通过且负责人确认后，才评估正式入口切换。

任一数据库初始化、迁移或恢复步骤失败，停止后续操作并保留日志。不要清空目标数据库重试，不要提前关闭 8600 服务。
