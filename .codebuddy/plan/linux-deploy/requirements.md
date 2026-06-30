# QmtQuant Linux 服务器部署需求文档

## 引言

QmtQuant 当前运行在 Mac/Windows 本地机器上，依赖 miniQMT 进行数据采集。为了让数据采集和 API 服务能够稳定运行在 Linux 服务器上，需要提供一套完整的 Linux 部署方案。

**核心架构**：
- **Windows 机器（内网）**：运行 miniQMT + xqshare server，作为数据源
- **Linux 服务器（内网）**：运行 QmtQuant，通过 xqshare client 远程连接 Windows，完成数据采集、Parquet 缓存写入，并对外提供 data-api HTTP 服务

**部署参数（用户已确认）**：
- Python 版本：3.13
- 项目目录：`/data/qmtquant`
- 数据同步定时策略：每天 17:00 触发
- data-api 监听端口：默认 8765，可通过 `.env` 配置

---

## 需求

### 需求 1：部署脚本（一键环境初始化）

**用户故事：** 作为运维人员，我希望有一个一键部署脚本，以便在全新 Linux 服务器上快速完成环境初始化，无需手动逐步操作。

#### 验收标准

1. WHEN 执行 `bash deploy/setup.sh` THEN 系统 SHALL 自动完成以下步骤：检查 Python 3.13 是否已安装、创建 `/data/qmtquant` 目录、创建 Python 虚拟环境（`/data/qmtquant/venv`）、安装 `requirements.txt` 中的全部依赖。
2. WHEN Python 3.13 未安装 THEN 脚本 SHALL 打印明确提示（包含安装建议命令），并退出，不继续执行后续步骤。
3. WHEN 虚拟环境已存在 THEN 脚本 SHALL 跳过创建步骤，直接执行依赖安装（幂等性）。
4. WHEN 脚本执行完成 THEN 系统 SHALL 打印"部署完成"摘要，列出已安装的关键依赖版本（Python、FastAPI、uvicorn、xqshare、pandas）。
5. WHEN 执行 `bash deploy/setup.sh --help` THEN 系统 SHALL 打印脚本用法说明。

---

### 需求 2：环境配置文件模板

**用户故事：** 作为运维人员，我希望有一个 Linux 专用的 `.env` 配置模板，以便快速填写 Windows xqshare server 的连接信息，无需从头查阅文档。

#### 验收标准

1. WHEN 项目中存在 `deploy/env.linux.example` 文件 THEN 该文件 SHALL 包含以下配置项（含中文注释说明）：
   - `XQSHARE_REMOTE_HOST`：Windows 机器内网 IP（必填）
   - `XQSHARE_REMOTE_PORT`：xqshare server 端口（默认 8888）
   - `DATA_API_HOST`：data-api 监听地址（默认 `0.0.0.0`）
   - `DATA_API_PORT`：data-api 监听端口（默认 8765）
2. WHEN 运维人员复制 `deploy/env.linux.example` 为 `.env` 并填写 IP 后 THEN 系统 SHALL 能正常连接 Windows xqshare server 并启动 data-api 服务。
3. IF `.env` 文件中 `XQSHARE_REMOTE_HOST` 为空或未设置 THEN 系统 SHALL 在启动时打印明确错误提示，指引用户配置该项。

---

### 需求 3：data-api 服务的 systemd 管理

**用户故事：** 作为运维人员，我希望 data-api 服务通过 systemd 管理，以便实现开机自启、崩溃自动重启，并通过标准 `systemctl` 命令控制服务生命周期。

#### 验收标准

1. WHEN 项目中存在 `deploy/qmtquant-api.service` 文件 THEN 该文件 SHALL 是合法的 systemd unit 文件，包含：
   - `WorkingDirectory=/data/qmtquant`
   - 使用虚拟环境中的 Python 执行 `python dm_cli.py data-api`
   - `Restart=on-failure`（崩溃自动重启）
   - `RestartSec=10`
   - 标准输出和错误输出重定向到 journald
2. WHEN 执行 `systemctl start qmtquant-api` THEN 系统 SHALL 启动 data-api 服务，可通过 `systemctl status qmtquant-api` 查看运行状态。
3. WHEN 执行 `systemctl enable qmtquant-api` THEN 系统 SHALL 设置开机自启。
4. WHEN data-api 进程意外崩溃 THEN systemd SHALL 在 10 秒后自动重启服务。
5. WHEN 执行 `journalctl -u qmtquant-api -f` THEN 系统 SHALL 实时显示 data-api 的日志输出。
6. WHEN `deploy/setup.sh` 执行时 THEN 脚本 SHALL 提供可选步骤：将 service 文件复制到 `/etc/systemd/system/` 并执行 `systemctl daemon-reload`（需要 sudo 权限，提示用户手动执行或自动执行）。

---

### 需求 4：数据同步定时任务（systemd timer）

**用户故事：** 作为运维人员，我希望数据同步任务通过 systemd timer 定时触发（每天 17:00），以便在 A 股收盘后自动完成数据采集，无需人工干预。

#### 验收标准

1. WHEN 项目中存在 `deploy/qmtquant-sync.service` 文件 THEN 该文件 SHALL 是合法的 systemd unit 文件（Type=oneshot），执行完整的数据同步流程：
   - 同步辅助数据（交易日历 + 合约信息）：`python dm_cli.py sync --asset stock --sub calendar,instrument`
   - 同步 K 线数据（沪深 A 股全量）：`python dm_cli.py sync --asset stock --sub kline --sector 沪深A股`
2. WHEN 项目中存在 `deploy/qmtquant-sync.timer` 文件 THEN 该文件 SHALL 配置为每天 `17:00:00` 触发（`OnCalendar=*-*-* 17:00:00`），并设置 `Persistent=true`（若错过触发时间则在下次启动时补跑）。
3. WHEN 执行 `systemctl enable --now qmtquant-sync.timer` THEN 系统 SHALL 激活定时任务，可通过 `systemctl list-timers` 查看下次触发时间。
4. WHEN 同步任务执行时 THEN 日志 SHALL 通过 journald 记录，可通过 `journalctl -u qmtquant-sync` 查看。
5. WHEN 需要手动触发同步 THEN 运维人员 SHALL 能通过 `systemctl start qmtquant-sync` 立即执行一次同步，无需等待定时器。

---

### 需求 5：部署文档（README）

**用户故事：** 作为运维人员，我希望有一份清晰的 Linux 部署文档，以便按步骤完成从零到运行的全流程部署，无需依赖口头传授。

#### 验收标准

1. WHEN 查阅 `deploy/README.md` THEN 文档 SHALL 包含以下章节：
   - **前置条件**：Python 3.13、内网连通性要求、Windows xqshare server 配置说明
   - **快速部署**：step-by-step 命令列表（克隆项目 → 运行 setup.sh → 配置 .env → 安装 systemd 服务 → 启动服务）
   - **验证部署**：如何确认 xqshare 连接正常、如何确认 data-api 服务正常（`curl http://localhost:8765/health`）
   - **日常运维**：查看日志、手动触发同步、重启服务的命令
   - **故障排查**：常见问题（xqshare 连不上、端口被占用、Python 版本不对）及解决方案
2. WHEN 文档中出现命令示例 THEN 所有命令 SHALL 使用 `/data/qmtquant` 作为项目路径，与实际部署路径一致。

---

### 需求 6：data-api 端口可配置化

**用户故事：** 作为运维人员，我希望 data-api 的监听端口可通过 `.env` 文件配置，以便在端口冲突时无需修改代码即可调整。

#### 验收标准

1. WHEN `.env` 中设置 `DATA_API_PORT=9000` THEN `python dm_cli.py data-api` 启动时 SHALL 自动读取该配置，监听 9000 端口，无需显式传入 `--port` 参数。
2. WHEN 命令行显式传入 `--port 8888` THEN 命令行参数 SHALL 优先于 `.env` 配置（命令行 > 环境变量 > 默认值）。
3. WHEN `.env` 中设置 `DATA_API_HOST=0.0.0.0` THEN 服务 SHALL 监听所有网络接口，允许局域网访问。
4. IF `DATA_API_PORT` 未在 `.env` 中设置 THEN 系统 SHALL 使用默认值 `8765`。
