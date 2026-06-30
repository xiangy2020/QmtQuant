# 实施计划：QmtQuant Linux 服务器部署

- [ ] 1. 创建 Linux 环境配置模板 `deploy/env.linux.example`
   - 包含 `XQSHARE_REMOTE_HOST`、`XQSHARE_REMOTE_PORT`、`DATA_API_HOST`、`DATA_API_PORT` 四个配置项
   - 每个配置项附带中文注释说明用途和默认值
   - _需求：2.1、2.2_

- [ ] 2. 实现 data-api 端口/Host 可配置化（读取 `.env`）
   - 修改 `dm_cli/cmd_data_api.py`，在解析命令行参数后，若 `--port`/`--host` 未显式传入，则从环境变量 `DATA_API_PORT`/`DATA_API_HOST` 读取（优先级：命令行 > 环境变量 > 默认值）
   - 在 `env.py` 中新增 `DATA_API_PORT`、`DATA_API_HOST` 常量的读取逻辑（统一从 `.env` 加载）
   - 启动时若 `XQSHARE_REMOTE_HOST` 为空，打印明确错误提示并退出
   - _需求：6.1、6.2、6.3、6.4、2.3_

- [ ] 3. 创建 data-api systemd 服务文件 `deploy/qmtquant-api.service`
   - `WorkingDirectory=/data/qmtquant`，使用 `/data/qmtquant/venv/bin/python` 执行 `dm_cli.py data-api`
   - 配置 `Restart=on-failure`、`RestartSec=10`，日志输出到 journald
   - 配置 `EnvironmentFile=/data/qmtquant/.env` 自动加载环境变量
   - _需求：3.1、3.2、3.3、3.4、3.5_

- [ ] 4. 创建数据同步 systemd 服务与定时器文件
   - `deploy/qmtquant-sync.service`：Type=oneshot，依次执行 `sync --asset stock --sub calendar,instrument` 和 `sync --asset stock --sub kline --sector 沪深A股`
   - `deploy/qmtquant-sync.timer`：`OnCalendar=*-*-* 17:00:00`，`Persistent=true`
   - _需求：4.1、4.2、4.3、4.4、4.5_

- [ ] 5. 编写一键部署脚本 `deploy/setup.sh`
   - 检查 Python 3.13 是否已安装，未安装则打印安装建议并退出
   - 幂等创建虚拟环境 `/data/qmtquant/venv` 并安装 `requirements.txt` 依赖
   - 脚本末尾打印关键依赖版本摘要（Python、FastAPI、uvicorn、pandas）
   - 提示用户手动执行 systemd 服务安装命令（复制 service 文件 + `systemctl daemon-reload`）
   - 支持 `--help` 参数打印用法说明
   - _需求：1.1、1.2、1.3、1.4、1.5、3.6_

- [ ] 6. 编写 Linux 部署文档 `deploy/README.md`
   - **前置条件**：Python 3.13 安装方式、内网连通性要求、Windows xqshare server 配置说明
   - **快速部署**：克隆项目 → 运行 setup.sh → 配置 .env → 安装 systemd 服务 → 启动服务的完整命令序列
   - **验证部署**：xqshare 连接验证命令、`curl http://localhost:8765/health` 验证 data-api
   - **日常运维**：查看日志、手动触发同步、重启服务的常用命令
   - **故障排查**：xqshare 连不上、端口被占用、Python 版本不对的解决方案
   - _需求：5.1、5.2_
