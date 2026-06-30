# Mac/Windows 跨平台联动指南（xqshare）

> **背景**：xtquant 核心模块是 Windows 专属编译库（`.pyd`），无法在 Mac 上运行。回测策略需要在 Mac 上执行，因此使用 [xqshare](https://github.com/xqshare/xqshare) 作为跨平台通信方案，将 Windows VM 上运行的 xtquant 能力透明地暴露给 Mac 端。

---

## 一、架构概览

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│         Mac（开发机）          │  RPyC   │       Windows VM（迅投 QMT）   │
│                              │  18812  │                              │
│  framework/core.py           │ ──────► │  xqshare server              │
│    └─ from xqshare import    │ ◄────── │    └─ xtquant（原生运行）      │
│         xtdata / xttrader    │         │         xtdata / xttrader    │
└──────────────────────────────┘         └──────────────────────────────┘
```

**核心原理**：xqshare 通过 RPyC（Remote Python Call）在 Mac 端创建 xtquant 模块的透明代理。Mac 端调用 `xtdata.get_market_data_ex(...)` 时，调用会自动通过 TCP 连接转发到 Windows VM 上的 xtquant 执行，结果原路返回。对上层代码完全透明，与在 Windows 本地调用 xtquant 的写法完全一致。

---

## 二、环境准备（Python 虚拟环境）

两端均使用 **Python 3.13** 虚拟环境，相互独立，互不干扰。

### 2.1 Mac 端创建虚拟环境

```bash
# 在项目根目录下创建虚拟环境
cd /path/to/QmtQuant
python3.13 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装项目依赖
pip install xqshare
pip install -r requirements.txt   # 如有
```

> 建议将 `.venv` 加入 `.gitignore`，不提交到版本库。

### 2.2 Windows VM 端创建虚拟环境

> **注意（Parallels 共享文件夹用户）**：虽然 Mac 和 Windows VM 共享同一个项目目录，但**不能共用 Mac 的 `venv/`**。虚拟环境是平台强绑定的：Mac 的 `venv/bin/` 是 macOS 二进制，Windows 无法执行；xtquant 的 C 扩展（`.pyd`）也只有 Windows 版本。因此必须在 Windows 端单独创建虚拟环境，使用不同目录名 `venv_win/` 避免冲突。

在 Windows VM 上打开 PowerShell，**直接进入共享的项目目录**：

```powershell
# 进入 Parallels 共享的项目目录（路径按实际情况调整）
cd "\\Mac\Home\Documents\AIWork\QmtQuant"

# 创建 Windows 专用虚拟环境（目录名与 Mac 的 venv/ 区分）
py -3.13 -m venv venv_win

# 激活虚拟环境
.\venv_win\Scripts\activate

# 安装依赖
pip install xqshare xtquant
```

> 如果 PowerShell 提示执行策略限制，先运行：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 2.3 验证环境（Windows VM）

Windows VM 端提供了 `config/check_env.py` 脚本，用于一键检测运行环境并生成配置文件：

```powershell
# 确保已激活虚拟环境，且 miniQMT 已登录运行
python config/check_env.py
```

脚本会依次检查并输出：

```
==================================================
🔍 开始检查运行环境
==================================================
Python版本: 3.13.x
Python路径: \\Mac\Home\Documents\AIWork\QmtQuant\venv_win\Scripts\python.exe
运行路径: \\Mac\Home\Documents\AIWork\QmtQuant

==================================================
📦 xtquant 模块检查
==================================================
✅ xtquant 已安装
xtquant 版本: x.x.x

==================================================
📊 miniQMT 终端状态
==================================================
miniQMT路径: C:\QMT\bin.x64
miniQMT窗口: 55011888 - 国金QMT交易端 1.0.0.xxxxx
状态: 🟢 运行中

==================================================
💡 环境检测配置
==================================================
✅ 环境准备就绪，可以开始使用 miniQMT 量化开发！
✅ 已生成 xqshare 服务端配置文件 .env：\\Mac\Home\Documents\AIWork\QmtQuant\config\.env
   QMT_USERDATA_PATH=C:\QMT\userdata_mini
   QMT_ACCOUNT_ID=55011888
```

脚本会自动生成 `.env` 文件，内容为标准 xqshare 服务端配置格式：
- `QMT_USERDATA_PATH`：`userdata_mini` 目录路径（xqshare server 启动时读取）
- `QMT_ACCOUNT_ID`：资金账号
- `XQSHARE_PORT`：服务端口（默认 18812）
- `LOG_LEVEL`：日志级别（默认 INFO）

> **注意**：`check_env.py` 仅在 Windows 上运行（依赖 Windows API），Mac 端无需执行。

---

## 三、Windows VM 端配置（一次性）

### 3.1 安装 xqshare

在 Windows VM 上打开命令行（确保已激活虚拟环境）：

```powershell
pip install xqshare
```

### 3.2 启动 xqshare server

运行 `config/check_env.py` 后，项目根目录下已自动生成 `.env` 配置文件。直接在项目目录下启动 xqshare server，它会自动读取当前目录的 `.env`：

```powershell
# 确保已激活虚拟环境，在项目根目录下执行
python -m xqshare.server --background
```

如需临时覆盖配置，也可通过环境变量方式启动：

```powershell
# 临时覆盖（按实际情况修改）
$env:XQSHARE_PORT = "18812"
$env:QMT_USERDATA_PATH = "C:\QMT\userdata_mini"
$env:QMT_ACCOUNT_ID = "你的资金账号"
$env:LOG_LEVEL = "INFO"

python -m xqshare.server
```

生成的 `.env` 文件内容示例：

```ini
# xqshare 服务端环境变量配置（由 check_env.py 自动生成）

XQSHARE_PORT=18812

QMT_USERDATA_PATH=C:\QMT\userdata_mini
QMT_ACCOUNT_ID=55011888

LOG_LEVEL=INFO
```

启动成功后，终端会显示：
```
INFO - xqshare server started on 0.0.0.0:18812
INFO - xtdata connected
INFO - xttrader connected
```

### 3.3 确认 VM 网络可达

确保 Mac 可以访问 Windows VM 的 18812 端口：

```bash
# 在 Mac 上测试连通性
nc -zv 10.211.55.3 18812
```

> **Parallels Desktop 用户**：Windows VM 的 IP 通常为 `10.211.55.3`，可在 VM 网络设置中确认。

---

## 四、Mac 端配置

### 4.1 安装 xqshare

```bash
pip install xqshare
```

### 4.2 配置连接参数

在项目根目录的 `.env` 文件中添加（参考 `xqshare/.env.client.example`）：

```ini
# xqshare 客户端配置

# Windows VM 地址
XQSHARE_REMOTE_HOST=10.211.55.3

# xqshare 服务端口
XQSHARE_REMOTE_PORT=18812

# 认证配置（如服务端未启用认证则留空）
XQSHARE_CLIENT_ID=
XQSHARE_CLIENT_SECRET=
```

> **说明**：xqshare 支持 HMAC token 认证，但默认不启用。本地开发场景下，服务端未配置 `clients.yaml` 时走默认账号，客户端**认证字段留空**即可正常连接。若填写了错误的 `client_id`/`client_secret`，服务端会返回"认证失败：无效的客户端凭证"。详见 [xqshare/README.md](../xqshare/README.md#认证机制)。

### 4.3 验证连接

xqshare 启动时会自动读取项目根目录下的 `.env` 文件（即 4.2 步配置的 `XQSHARE_REMOTE_HOST` 和 `XQSHARE_REMOTE_PORT`），无需手动传入连接参数：

**方式一：命令行工具快速验证（推荐）**

```bash
# 设置环境变量后直接调用命令行工具（xqshare 安装后自带）
export XQSHARE_REMOTE_HOST="10.211.55.3"
xtdata get_stock_list_in_sector --sector-name "沪深A股" --limit 10
```

> 命令行工具不传认证参数时走服务端默认账号，是最快的连通性验证方式。详见 [xqshare/README.md](../xqshare/README.md#命令行工具)。

**方式二：Python API 验证**

```python
import xqshare

# xqshare 自动从 .env 读取 XQSHARE_REMOTE_HOST / XQSHARE_REMOTE_PORT
xqshare.connect()

# 连接成功后即可使用 xtdata
xtdata = xqshare.xtdata
result = xtdata.get_trading_dates("SH", count=5)
print(result)  # 应输出最近 5 个交易日
```

> 如果 `.env` 不存在或需要临时覆盖，也可以显式传参：`xqshare.connect(host="10.211.55.3", port=18812)`

---

## 五、在 QmtQuant 项目中使用

### 5.1 导入方式

项目中所有文件已统一通过条件导入处理平台差异，**无需手动判断平台**：

```python
# 项目核心模块顶部（如 framework/core.py、utils/strategy_utils.py 等）
import platform as _platform
if _platform.system() == "Darwin":
    # Mac 平台：使用 xqshare 远程代理
    from xqshare import xtdata
else:
    # Windows 平台：使用原生 xtquant
    from xtquant import xtdata
```

### 5.2 调用方式（与 Windows 本地完全一致）

```python
# 获取 K 线数据
data = xtdata.get_market_data_ex(
    field_list=["open", "high", "low", "close", "volume"],
    stock_list=["000001.SZ", "600000.SH"],
    period="1d",
    start_time="20240101",
    end_time="20241231",
)

# 获取板块成分股
stocks = xtdata.get_stock_list_in_sector("沪深300")

# 下载历史数据
xtdata.download_history_data2(
    stock_list=["000001.SZ"],
    period="1d",
    start_time="20200101",
)

# 获取交易日历
dates = xtdata.get_trading_dates("SH", start_time="20240101", end_time="20241231")
```

### 5.3 交易接口（实盘）

```python
from xqshare import xttrader, xttype

# 创建账户对象
account = xttype.StockAccount("你的资金账号")

# 查询持仓
positions = xttrader.query_stock_positions(account)

# 下单
order_id = xttrader.order_stock(
    account=account,
    stock_code="000001.SZ",
    order_type=xtconstant.STOCK_BUY,
    order_volume=100,
    price_type=xtconstant.FIX_PRICE,
    price=10.50,
)
```

---

## 六、常见问题

### Q1：连接超时 / 连接被拒绝

**排查步骤：**
1. 确认 Windows VM 上 xqshare server 已启动
2. 确认 VM 防火墙允许 18812 端口入站
3. 用 `nc -zv <VM_IP> 18812` 测试端口连通性
4. 检查 `.env` 中的 `XQSHARE_REMOTE_HOST` 是否正确（Parallels 用户通常为 `10.211.55.3`）
5. 用命令行工具做最小化验证，排除认证问题：
   ```bash
   export XQSHARE_REMOTE_HOST="10.211.55.3"
   xtdata get_stock_list_in_sector --sector-name "沪深A股" --limit 5
   ```
6. 若命令行通但 Python API 报"认证失败"，检查 `.env` 中 `XQSHARE_CLIENT_ID` / `XQSHARE_CLIENT_SECRET` 是否留空（不能填写占位符）

### Q2：xtdata 返回空数据

**可能原因：**
- QMT 客户端未在 Windows VM 上运行（需要先启动 QMT）
- 数据未下载到本地，需先调用 `download_history_data2` 下载

### Q3：回调函数不触发

xqshare 通过 `BgServingThread` 处理回调，需要在主线程保持事件循环：

```python
from rpyc.utils.helpers import BgServingThread

# 订阅行情后，启动后台服务线程接收回调
bg = BgServingThread(xqshare.get_client().conn)
xtdata.subscribe_quote("000001.SZ", period="1m", callback=my_callback)
# ... 主线程继续运行
```

### Q4：Mac 上如何确认 xqshare 版本

```bash
pip show xqshare
# 或
python -c "import xqshare; print(xqshare.__version__)"
```

---

## 七、相关文件索引

| 文件 | 运行环境 | 职责 |
|------|---------|------|
| `xqshare/xqshare/server.py` | Windows VM | xqshare 服务端，封装 xtquant 为 RPyC 服务 |
| `xqshare/xqshare/client.py` | Mac | xqshare 客户端，提供透明代理对象 |
| `xqshare/README.md` | - | xqshare 完整文档：安装、配置、API、认证、命令行工具等 |
| `config/check_env.py` | Windows VM | 一键检测运行环境，自动生成 `.env`（含 userdata 路径 + 资金账号，供 xqshare server 直接读取） |
| `framework/core.py` | Mac | 回测框架，通过 `from xqshare import xtdata` 调用数据 |
| `utils/strategy_utils.py` | Mac | 行情工具函数，同上 |
| `xqshare/.env.server.example` | Windows VM | 服务端配置模板 |
| `xqshare/.env.client.example` | Mac | 客户端配置模板 |

> 相关文档：[start_run_flow.md](start_run_flow.md) — 启动运行完整流程说明


