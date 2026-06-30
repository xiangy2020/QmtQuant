# miniQMT 守护进程使用说明

## 一、背景与目的

本项目采用 **Mac + Windows VM 跨平台架构**：

```
┌──────────────────────┐   RPyC/18812   ┌──────────────────────────┐
│   Mac（开发/回测机）   │ ─────────────► │   Windows VM（迅投 QMT）  │
│   框架核心 / 策略代码  │ ◄───────────── │   xqshare server         │
└──────────────────────┘                │   XtMiniQmt.exe          │
                                        └──────────────────────────┘
```

整个数据链路的稳定性依赖 Windows 侧**两个进程**持续运行：

| 进程 | 作用 |
|------|------|
| `XtMiniQmt.exe` | 迅投 miniQMT 行情/交易终端，提供 xtdata/xttrader 能力 |
| `python -m xqshare.server` | 跨平台 RPC 桥接服务，将 xtdata 能力透明暴露给 Mac 端 |

任意一个进程崩溃，Mac 端所有数据请求都会失败。守护进程的目的就是**持续监控这两个进程，崩溃后自动重启，减少人工干预**。

---

## 二、相关文件

| 文件 | 说明 |
|------|------|
| `config/qmt_watchdog.py` | 守护进程主脚本，负责监控与自动重启 |
| `config/setup_autostart.py` | 开机自启动注册工具，通过 Windows 任务计划程序实现 |
| `logs/qmt_watchdog.log` | 运行日志（自动创建，5 MB 轮转，保留 3 个历史文件） |

---

## 三、工作原理

### 3.1 整体流程

```
守护进程启动
  │
  ├─ 读取 .env 配置（QMT_EXE_PATH、检查间隔等）
  ├─ 初始化日志（控制台 + 文件双通道）
  ├─ 创建 ProcessWatcher × 2（miniQMT、xqshare-server）
  │
  └─ 主循环（每 WATCHDOG_CHECK_INTERVAL 秒执行一轮）
       │
       ├─ [miniQMT] is_running()？
       │     ├─ 是 → 无操作（状态变化时记 INFO 日志）
       │     └─ 否 → try_restart() → 等待就绪 → 更新失败计数
       │
       └─ [xqshare-server] is_running()？
             ├─ 是 → 无操作
             └─ 否 → try_restart() → 等待就绪 → 更新失败计数
```

### 3.2 进程检测方式

- **miniQMT**：通过 `psutil` 遍历系统进程，按**进程名** `XtMiniQmt.exe` 匹配（大小写不敏感）
- **xqshare server**：按**命令行参数**包含 `xqshare.server` 字符串匹配，兼容不同 Python 路径

### 3.3 自动重启逻辑

1. 检测到进程不存在时，调用 `subprocess.Popen` 启动目标程序
2. 启动命令发出后，等待 `WATCHDOG_STARTUP_WAIT` 秒（默认 5 秒）让进程就绪
3. 若启动失败（路径不存在、权限不足等），记录 ERROR 日志，下一轮继续重试
4. **连续失败次数达到 `WATCHDOG_MAX_RETRIES`（默认 3 次）后**，记录 CRITICAL 日志并暂停该进程的重启，等待人工介入
5. 两个进程的监控**相互独立**，一个暂停不影响另一个

### 3.4 日志级别说明

| 级别 | 触发场景 |
|------|---------|
| `INFO` | 守护进程启动/停止、进程初始状态、进程恢复运行、启动命令发出 |
| `WARNING` | 进程意外退出、`QMT_EXE_PATH` 未配置或路径无效 |
| `ERROR` | 单次重启失败（路径不存在、权限不足等） |
| `CRITICAL` | 连续重启失败达上限，已暂停重启，需人工介入 |

### 3.5 开机自启动原理

`setup_autostart.py` 通过 Windows 内置的 `schtasks` 命令行工具操作任务计划程序：

- **触发时机**：`ONLOGON`（用户登录时），比 `ONSTART` 更可靠，无需 SYSTEM 权限
- **运行方式**：使用 `pythonw.exe`（无窗口后台运行），路径含空格时自动加引号
- **权限**：`/RL HIGHEST` 以最高权限运行，避免启动 miniQMT 时遇到 UAC 弹窗
- **幂等**：`/F` 参数保证重复执行 `install` 会覆盖旧任务，不报错

---

## 四、配置说明

所有配置项写入项目根目录的 `.env` 文件：

```ini
# ==================== miniQMT 路径（必填）====================
# miniQMT 可执行文件路径，缺失则跳过 miniQMT 监控，仅监控 xqshare server
QMT_EXE_PATH=C:\国金证券QMT交易端\bin.x64\XtItClient.exe

# ==================== 守护进程参数（可选）====================
# 检查间隔秒数，默认 30
WATCHDOG_CHECK_INTERVAL=30

# 最大连续重启失败次数，超过后暂停重启等待人工介入，默认 3
WATCHDOG_MAX_RETRIES=3

# 进程启动后等待就绪的秒数，默认 5
WATCHDOG_STARTUP_WAIT=5
```

> **注意**：`QMT_EXE_PATH` 填写的是 `XtItClient.exe`（登录客户端），守护进程启动它后，miniQMT 内核进程 `XtMiniQmt.exe` 会随之启动。守护进程检测的是 `XtMiniQmt.exe` 是否存活。

---

## 五、使用步骤

### 5.1 前置条件

在 Windows 端激活项目虚拟环境，确保已安装 `psutil`：

```powershell
# 进入项目目录并激活虚拟环境
cd "\\Mac\Home\Documents\AIWork\QmtQuant"
.\venv_win\Scripts\activate

# 确认 psutil 已安装
pip install psutil
```

### 5.2 手动启动守护进程（临时运行）

```powershell
python config/qmt_watchdog.py
```

启动后终端会持续输出日志，按 `Ctrl+C` 可优雅停止。

### 5.3 注册开机自启动（推荐）

**以管理员身份**打开 PowerShell，激活虚拟环境后执行：

```powershell
# 注册开机自启动
python config/setup_autostart.py install

# 验证注册状态
python config/setup_autostart.py status
```

注册成功后，**每次电脑重启并登录，守护进程会自动在后台无窗口运行**。

### 5.4 注销开机自启动

```powershell
python config/setup_autostart.py uninstall
```

### 5.5 查看运行日志

```powershell
# 实时查看最新日志
Get-Content logs\qmt_watchdog.log -Wait -Tail 50
```

或直接用文本编辑器打开 `logs/qmt_watchdog.log`。

---

## 六、常见问题

**Q：注册开机自启动时提示"拒绝访问"？**
> 需要以管理员身份运行 PowerShell：右键 PowerShell 图标 → 以管理员身份运行。

**Q：守护进程启动了，但 miniQMT 没有自动重启？**
> 检查 `.env` 中 `QMT_EXE_PATH` 是否正确，路径中的反斜杠需要写单个 `\`（`.env` 文件中不需要转义）。可查看 `logs/qmt_watchdog.log` 中的 ERROR 日志确认具体原因。

**Q：日志中出现 CRITICAL，守护进程停止重启了怎么办？**
> 说明连续 3 次（默认）重启均失败，需要人工检查：
> 1. 确认 `QMT_EXE_PATH` 路径是否存在
> 2. 手动尝试启动 miniQMT，确认是否有报错
> 3. 排查后重启守护进程即可恢复监控（`suspended` 状态在进程重启后会自动重置）

**Q：xqshare server 重启后 Mac 端连接能自动恢复吗？**
> xqshare server 重启后会重新监听端口，Mac 端下次发起 RPC 调用时会自动重连（取决于 xqshare client 的重连策略）。

**Q：可以只监控其中一个进程吗？**
> 可以。不配置 `QMT_EXE_PATH` 时，守护进程自动跳过 miniQMT 监控，仅监控 xqshare server。目前不支持单独跳过 xqshare server 监控（如有需要可修改 `main()` 函数）。
