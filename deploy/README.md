# QmtQuant Linux 服务器部署指南

本文档说明如何将 QmtQuant 数据采集服务和 Data API 服务部署到 Linux 服务器（内网环境）。

## 架构说明

```
Windows 机器（内网）                    Linux 服务器（内网）
┌─────────────────────┐                ┌──────────────────────────────┐
│  miniQMT            │                │  /data/qmtquant/             │
│  xqshare server     │◄──── rpyc ────►│  xqshare client              │
│  （数据源）          │   内网连接      │  ↓                           │
└─────────────────────┘                │  数据采集 → Parquet 缓存      │
                                       │  ↓                           │
                                       │  data-api（FastAPI :8765）   │
                                       └──────────────────────────────┘
```

---

## 一、前置条件

### 1.1 Python 3.13

Linux 服务器需安装 Python 3.13。

**Ubuntu / Debian：**
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev
```

**CentOS / RHEL / Rocky Linux：**
```bash
sudo dnf install python3.13 python3.13-devel
```

验证安装：
```bash
python3.13 --version
# 期望输出：Python 3.13.x
```

### 1.2 内网连通性要求

- Linux 服务器与 Windows 机器必须在同一内网，或通过 VPN 互通
- Linux 服务器需能访问 Windows 机器的 xqshare server 端口（默认 `18812`）
- 验证连通性：
  ```bash
  # 替换为 Windows 机器的实际 IP
  nc -zv 192.168.1.100 18812
  ```

### 1.3 Windows xqshare server 配置

Windows 机器上的 xqshare server 必须：
1. 已启动并监听 `0.0.0.0`（允许局域网连接，而非仅 `127.0.0.1`）
2. 防火墙已放行 `18812` 端口（入站规则）
3. miniQMT 已登录并运行

---

## 二、快速部署

### 步骤 1：克隆项目

```bash
# 将项目克隆到 /data/qmtquant
sudo mkdir -p /data
sudo git clone <仓库地址> /data/qmtquant
cd /data/qmtquant
```

### 步骤 2：运行一键初始化脚本

```bash
bash deploy/setup.sh
```

脚本将自动完成：
- 检查 Python 3.13
- 创建虚拟环境 `/data/qmtquant/venv`
- 安装 `requirements.txt` 全部依赖
- 打印关键依赖版本摘要
- 提示 systemd 服务安装命令

> 如需查看脚本用法：`bash deploy/setup.sh --help`

### 步骤 3：配置 .env

```bash
# 复制配置模板
cp /data/qmtquant/deploy/env.linux.example /data/qmtquant/.env

# 编辑配置，填写 Windows 机器 IP
vim /data/qmtquant/.env
```

**必填项：**
```ini
# Windows 机器的内网 IP（运行 miniQMT + xqshare server 的机器）
XQSHARE_REMOTE_HOST=192.168.1.100
```

**可选项（按需修改）：**
```ini
XQSHARE_REMOTE_PORT=18812   # xqshare server 端口，默认 18812
DATA_API_HOST=0.0.0.0       # data-api 监听地址，0.0.0.0 允许局域网访问
DATA_API_PORT=8765           # data-api 监听端口，默认 8765
```

### 步骤 4：安装 systemd 服务

```bash
# 复制服务文件
sudo cp /data/qmtquant/deploy/qmtquant-api.service  /etc/systemd/system/
sudo cp /data/qmtquant/deploy/qmtquant-sync.service /etc/systemd/system/
sudo cp /data/qmtquant/deploy/qmtquant-sync.timer   /etc/systemd/system/

# 重新加载 systemd 配置
sudo systemctl daemon-reload
```

### 步骤 5：启动服务

```bash
# 启动 data-api 服务并设置开机自启
sudo systemctl enable --now qmtquant-api

# 启动数据同步定时器并设置开机自启（每天 17:00 自动同步）
sudo systemctl enable --now qmtquant-sync.timer
```

---

## 三、验证部署

### 3.1 验证 xqshare 连接

```bash
cd /data/qmtquant
source venv/bin/activate

# 测试 xqshare 连接（会打印平台环境信息）
python -c "from env import xtdata, print_env_info; print_env_info(); print('xtdata:', xtdata)"
```

期望输出中 `xtdata` 不为 `None`，且显示已连接的 IP 和端口。

### 3.2 验证 data-api 服务

```bash
# 查看服务状态
sudo systemctl status qmtquant-api

# 调用健康检查接口
curl http://localhost:8765/health
```

期望返回：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok",
    "version": "x.x.x",
    "cache_root": "/root/.qmtquant/cache",
    ...
  }
}
```

### 3.3 验证定时器

```bash
# 查看定时器状态和下次触发时间
systemctl list-timers qmtquant-sync.timer
```

---

## 四、日常运维

### 查看日志

```bash
# 实时查看 data-api 日志
journalctl -u qmtquant-api -f

# 查看最近 100 行 data-api 日志
journalctl -u qmtquant-api -n 100

# 查看数据同步任务日志
journalctl -u qmtquant-sync -n 100

# 查看今天的所有 QmtQuant 相关日志
journalctl -u qmtquant-api -u qmtquant-sync --since today
```

### 手动触发数据同步

```bash
# 立即执行一次数据同步（无需等待 17:00 定时器）
sudo systemctl start qmtquant-sync

# 查看同步执行结果
journalctl -u qmtquant-sync -n 50
```

### 重启服务

```bash
# 重启 data-api 服务
sudo systemctl restart qmtquant-api

# 停止 data-api 服务
sudo systemctl stop qmtquant-api

# 停止定时器（暂停自动同步）
sudo systemctl stop qmtquant-sync.timer
```

### 手动执行 CLI 命令

```bash
cd /data/qmtquant
source venv/bin/activate

# 手动同步交易日历和合约信息
python dm_cli.py sync --asset stock --sub calendar,instrument

# 手动同步沪深A股 K 线数据
python dm_cli.py sync --asset stock --sub kline --sector 沪深A股

# 查看缓存统计
python dm_cli.py stats

# 启动 data-api（前台运行，调试用）
python dm_cli.py data-api --host 0.0.0.0 --port 8765
```

---

## 五、故障排查

### 问题 1：xqshare 连不上

**现象：** `env.py` 报错 `xqshare 连接失败` 或 `xtdata` 为 `None`

**排查步骤：**

1. 确认 `.env` 中 `XQSHARE_REMOTE_HOST` 已填写正确 IP：
   ```bash
   grep XQSHARE_REMOTE_HOST /data/qmtquant/.env
   ```

2. 测试网络连通性：
   ```bash
   nc -zv <Windows IP> 18812
   # 期望：Connection to <IP> 18812 port [tcp/*] succeeded!
   ```

3. 确认 Windows 机器上 xqshare server 已启动，且监听 `0.0.0.0`（非 `127.0.0.1`）

4. 检查 Windows 防火墙是否放行 `18812` 端口（入站规则）

5. 确认端口号与 Windows 上 xqshare server 配置一致（`.env` 中 `XQSHARE_REMOTE_PORT`）

---

### 问题 2：data-api 端口被占用

**现象：** `systemctl start qmtquant-api` 失败，日志显示 `端口 8765 已被占用`

**解决方案：**

```bash
# 查看占用端口的进程
sudo ss -tlnp | grep 8765
# 或
sudo lsof -i :8765

# 方案 A：修改 data-api 端口
vim /data/qmtquant/.env
# 修改：DATA_API_PORT=9000
sudo systemctl restart qmtquant-api

# 方案 B：停止占用端口的进程（确认安全后执行）
sudo kill <PID>
sudo systemctl start qmtquant-api
```

---

### 问题 3：Python 版本不对

**现象：** `setup.sh` 报错 `未找到 Python 3.13`，或运行时出现语法错误

**解决方案：**

```bash
# 确认系统中的 Python 版本
python3 --version
python3.13 --version

# Ubuntu/Debian 安装 Python 3.13
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev

# 重新运行部署脚本
bash /data/qmtquant/deploy/setup.sh
```

---

### 问题 4：data-api 服务启动后立即退出

**现象：** `systemctl status qmtquant-api` 显示 `failed` 或 `inactive`

**排查步骤：**

```bash
# 查看详细错误日志
journalctl -u qmtquant-api -n 50 --no-pager

# 常见原因：
# 1. .env 文件不存在或 XQSHARE_REMOTE_HOST 未填写
ls -la /data/qmtquant/.env
grep XQSHARE_REMOTE_HOST /data/qmtquant/.env

# 2. 虚拟环境不存在或依赖未安装
ls /data/qmtquant/venv/bin/python
/data/qmtquant/venv/bin/python -c "import fastapi; import uvicorn; print('OK')"

# 3. 手动前台运行排查具体错误
cd /data/qmtquant
/data/qmtquant/venv/bin/python dm_cli.py data-api
```

---

### 问题 5：数据同步失败

**现象：** `journalctl -u qmtquant-sync` 显示同步错误

**排查步骤：**

```bash
# 查看同步日志
journalctl -u qmtquant-sync -n 100 --no-pager

# 手动执行同步命令，观察详细输出
cd /data/qmtquant
source venv/bin/activate
python dm_cli.py sync --asset stock --sub calendar,instrument
python dm_cli.py sync --asset stock --sub kline --sector 沪深A股
```

常见原因：xqshare 连接中断（Windows 机器重启或 miniQMT 退出），重新连接后重试即可。

---

## 六、文件清单

| 文件 | 说明 |
|------|------|
| `deploy/env.linux.example` | Linux 环境配置模板，复制为 `.env` 后填写 |
| `deploy/setup.sh` | 一键环境初始化脚本 |
| `deploy/qmtquant-api.service` | data-api systemd 服务单元文件 |
| `deploy/qmtquant-sync.service` | 数据同步 systemd 服务单元文件（oneshot） |
| `deploy/qmtquant-sync.timer` | 数据同步 systemd 定时器（每天 17:00） |
