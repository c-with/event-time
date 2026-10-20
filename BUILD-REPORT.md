# Event Time V0.4.1 — 构建与静态验证报告

## 已有验证证据

根据本次源码提交随附的开发机回报：

- `python -m unittest discover -s tests -v`：4/4 PASS，覆盖不同字段并发合并、同字段冲突保留服务端值、并发新增、冲突字段之外的修改保存。
- Python 核心文件 `py_compile`：通过。
- `node --check static/app.js`：通过。
- `bash -n`：部署与运维 Shell 脚本语法通过。
- Compose YAML 解析：通过。
- 安全检查：提交包未发现 `.env`、生产数据库、生产附件或硬编码凭证；`.env.example` 使用占位值。

这些是开发机报告记录的检查结果，不代表本报告作者已在 WS 上重跑所有检查。

## 尚未完成的集成验收

- 未在目标 WS 环境构建并启动真实 Docker 镜像。
- 未连接 WS PostgreSQL 执行真实 schema 初始化、连接与事务测试。
- 未完成 SQLite 旧库到 V0.4.1 规范化模型的完整迁移、数量对账和附件迁移。
- 未完成真实浏览器、多人并发、iPhone/Android HEIC/HEIF、反向代理 HTTPS 分享链接、大文件上传和恢复演练。
- 当前 `deploy.sh` 暴露的旧版导入命令是 JSON 导入；直接 SQLite 迁移流程尚未完成集成验证。不要把备份脚本存在误认为迁移链已通过。

## 交付结论

V0.4.1 是部署候选源码。4/4 单元测试与静态检查通过，不等于 PostgreSQL、Docker 或生产验收通过。所有切换门禁须按 `ACCEPTANCE-CHECKLIST.md` 在独立测试入口执行。

## 安全边界

- 新服务默认只绑定 `127.0.0.1:8601`。
- 不自动修改 Nginx Proxy Manager 正式入口。
- 旧 8600/SQLite 服务在验收期保持原样。
