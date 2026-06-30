# 启动运行完整流程说明

> 本文档描述通过 CLI 入口 (`bt_cli.py`) 启动策略后，系统从 CLI 层到框架层的完整执行链路。
> 涉及文件：`bt_cli.py`、`framework/core.py`、`framework/callbacks.py`。

---

## 一、整体流程概览

启动后，整个流程分为 **5 个阶段**：

```
bt_cli.py run <config.qmt>
    │
    ▼
【阶段 1】CLI 层处理          bt_cli.py  cmd_run()
    │  加载配置 → 写临时文件 → 实例化回调
    │
    ▼
【阶段 2】框架初始化           framework/core.py  QuantFramework.run()
    │  初始化账户 → 下载数据（可选）→ 加载股票池 → 调用策略 init()
    │
    ▼
【阶段 3】回测主循环           framework/core.py  _run_backtest()
    │  拉取历史 K 线 → 构建时间轴 → 逐 bar 驱动策略回调
    │
    ▼
【阶段 4】结果记录             framework/core.py  record_results()
    │  每日统计 / 交易记录 / 汇总指标 → 写入 backtest_results/
    │
    ▼
【阶段 5】结束收尾             bt_cli.py  _print_result_summary()
       终端打印核心指标
```

---

## 二、阶段 1：CLI 层处理

**入口**：`bt_cli.py` → `cmd_run()`

### 执行步骤

1. **创建 `CliFrameworkCallbacks` 实例**  
   实现 `FrameworkCallbacks` 协议，将框架回调输出到终端：
   - `on_log` → 根据 verbose 模式输出到 stdout
   - `on_progress` → 更新进度信息
   - `on_period_mismatch` → 打印警告后默认返回 `True`（不阻塞）
   - `on_t0_warning` → 打印 T+0 警告
   - `on_finished` → 标记运行结束

2. **读取配置参数**  
   - 从 `.qmt` 配置文件和 CLI 参数读取配置
   - `init_data_enabled`：通过 `--init-data` 参数控制
   - `risk_free_rate`：通过 `--risk-free-rate` 参数或 `.qmt` 配置文件读取

3. **写入临时配置文件**  
   将最终配置写入 `config/temp_bt_cli_config.qmt`

4. **调用 `QuantFramework.run()`**  
   传入临时配置文件路径、`CliFrameworkCallbacks` 实例、`init_data_enabled`、`risk_free_rate`。

---

## 三、阶段 2：框架初始化

**入口**：`framework/core.py` → `QuantFramework.run()`

### 执行步骤

#### 2.1 初始化交易接口和账户
调用 `init_trader_and_account()`，固定为回测模式，在内存中创建虚拟账户：
```python
trade_mgr.assets = {
    "cash":         init_capital,   # 来自配置文件
    "frozen_cash":  0.0,
    "market_value": 0.0,
    "total_asset":  init_capital,
}
trade_mgr.positions = {}  # 初始持仓为空
```

#### 2.2 数据初始化（可选，受设置控制）
`init_data_enabled` 由 CLI 层从 `--init-data` 参数读取后显式传入 `framework.run(init_data_enabled=...)`。

- **`True`（启用）**：调用 `init_data()`，对股票池中所有股票批量下载历史 K 线数据：
  ```python
  xtdata.download_history_data2(
      stock_codes,
      period=config.kline_period,       # 如 "1m"
      start_time=config.backtest_start,
      end_time=config.backtest_end,
      incrementally=True,               # 增量下载，已有数据不重复下载
  )
  ```

- **`False`（禁用，默认值）**：跳过下载，直接使用本地已有数据。

> 默认值为 `False`（不下载）。CLI 层通过 `--init-data` 参数控制。

#### 2.3 加载股票池
调用 `get_stock_list()`，优先从配置文件的 `stock_list` 字段读取（即配置文件中的股票代码列表）。

#### 2.4 判断股票池类型与交易模式
- `determine_pool_type(stock_codes)` → 判断是纯股票 / 纯 ETF / 混合，设置价格精度
- `check_t0_support(stock_codes)` → 判断是否启用 T+0 模式（仅全部为 T0 型 ETF 时启用）

#### 2.5 调用策略 `init()`
构建初始 `context` 字典，调用策略文件的 `init(stock_codes, context)`：
```python
context = {
    "__current_time__": { "timestamp", "datetime", "date", "time" },
    "__account__":       trade_mgr.assets,
    "__positions__":     trade_mgr.positions,
    "__stock_list__":    stock_codes,
    "__framework__":     self,   # QuantFramework 实例
}
```
策略在此完成自定义初始化（如全市场缓存预热、崩溃恢复等）。

---

## 四、阶段 3：回测主循环

**入口**：`framework/core.py` → `_run_backtest()`

### 4.1 准备阶段

1. **创建回测结果目录**  
   路径格式：`backtest_results/strategy_{hash}_{start}_{end}_{timestamp}/`

2. **下载基准指数日线数据**  
   调用 `xtdata.download_history_data(benchmark_code, period='1d', ...)` 并缓存到 `benchmark.csv`。

3. **批量拉取历史 K 线**  
   对股票池中每只股票调用 `xtdata.get_market_data_ex()`，读取本地已缓存的历史数据，存入 `historical_data` 字典。

4. **构建时间轴 `all_times`**  
   从所有股票的数据中提取时间戳，去重排序，得到回测期间所有触发时间点的有序列表。

### 4.2 主循环逻辑

```
for current_time in all_times:
    │
    ├─ 【新交易日检测】current_date != time_info["date"]
    │       ├─ 执行前一天盘后回调 on_post_market(post_data)
    │       ├─ T+1 模式：更新 can_use_volume = volume
    │       └─ 执行盘前回调 on_pre_market(pre_data)（若启用）
    │
    ├─ 【触发器检查】trigger.should_trigger(current_time, data)
    │       └─ 不触发 → continue（跳过本时间点）
    │
    ├─ 【风控检查】risk_mgr.check_risk(current_data)
    │       └─ 触发风控 → continue
    │
    ├─ 【非交易日过滤】tools.is_trade_day(date) == False → continue
    │
    ├─ 【调用策略主回调】signals = strategy.on_bar(current_data)
    │
    ├─ 【处理信号价格精度】round(price, price_decimals)
    │
    ├─ 【执行虚拟撮合】trade_mgr.process_signals(signals)
    │       ├─ 买入：检查资金 → 冻结资金 → 更新持仓
    │       └─ 卖出：检查持仓 → 释放资金 → 更新持仓
    │
    └─ 【记录结果】record_results(current_time, current_data, signals)
```

`current_data` 字典结构（每个时间点传入策略的完整数据）：
```python
current_data = {
    "__current_time__": { "timestamp", "datetime", "date", "time" },
    "__account__":       trade_mgr.assets,
    "__positions__":     trade_mgr.positions,
    "__stock_list__":    stock_codes,
    "__framework__":     self,
    "000001.SZ":         pd.Series({ "open", "high", "low", "close", "volume", ... }),
    "600000.SH":         pd.Series({ ... }),
    # ... 其他股票
}
```

### 4.3 盘后回调触发时机

盘后回调（`on_post_market`）在**每个新交易日的第一根 bar 到来时**，针对**前一天**触发，而非在当天收盘后立即触发。最后一个交易日的盘后回调在主循环结束后单独执行。

---

## 五、阶段 4：结果记录

每个触发时间点执行 `record_results()`，累积以下数据：

| 数据类型 | 内容 | 输出文件 |
|---------|------|------|
| 交易记录 | 每笔买卖的时间、代码、价格、数量、原因 | `trades.csv` |
| 每日统计 | 每日总资产、持仓市值、可用资金、基准收益 | `daily_stats.csv` |
| 基准数据 | 基准指数每日收盘价 | `benchmark.csv` |
| 汇总指标 | 全量评估指标（见下表） | `summary.csv` |

**`summary.csv` 字段说明：**

| 字段 | 说明 | 不可用时 |
|------|------|--------|
| `init_capital` | 初始资金（元） | — |
| `final_capital` | 最终资产（元） | — |
| `total_return` | 总收益率（%） | — |
| `annual_return` | 年化收益率（%） | — |
| `max_drawdown` | 最大回撤（%） | — |
| `trade_days` | 回测交易日数 | — |
| `sharpe_ratio` | 夏普比率 | `None`（日收益率数据不足） |
| `sortino_ratio` | 索提诺比率 | `None`（日收益率数据不足） |
| `volatility` | 年化波动率（小数形式，如 0.15 表示 15%） | `None`（日收益率数据不足） |
| `alpha` | 阿尔法（超额收益） | `None`（基准数据不足） |
| `beta` | 贝塔（市场相关性） | `None`（基准数据不足） |
| `win_rate` | 胜率（%） | `None`（无交易记录） |
| `profit_loss_ratio` | 盈亏比（平均盈利 / 平均亏损） | `None`（无亏损交易） |
| `risk_free_rate` | 计算时使用的无风险利率（小数形式） | — |
---

## 六、阶段 5：结束收尾

1. `_run_backtest()` 执行完毕，`is_running = False`
2. 框架调用 `callbacks.on_finished()`，`CliFrameworkCallbacks` 标记结束
3. CLI 主流程读取最新的 `backtest_results/` 目录
4. 自动读取 `summary.csv` 打印核心指标到终端：
   - 总收益率、年化收益率、最大回撤
   - 交易日数、交易笔数
   - 夏普比率、索提诺比率等

---

## 七、Mac 端代理链路说明

在 Mac 上运行时，`xtdata` 实际上是 `xtdata_proxy`，所有数据请求经由 HTTP 代理转发到 Windows VM：

```
Mac 端 (framework/core.py)
  └─ xtdata.download_history_data2() / get_market_data_ex()
       └─ xtdata_proxy/proxy.py
            └─ POST/GET http://10.211.55.3:8888/...
                 └─ Windows VM: miniqmt/gateway/server.py
                      └─ 真正调用 QMT 本地 xtdata 引擎
```

下载任务采用**异步 + 轮询**模式：
- Mac 端发起请求后立即获得 `task_id`
- 每 3 秒轮询 `/download/status/{task_id}`
- Windows 端完成后返回 `done`，Mac 端继续执行

---

## 八、关键配置项速查

| 配置项 | 存储位置 | 说明 |
|--------|---------|------|
| `init_data_enabled` | CLI：`--init-data` 参数 | 是否在启动时下载历史数据，默认 `False`；由调用方读取后显式传入框架 |
| `risk_free_rate` | CLI：`--risk-free-rate` 参数；`.qmt` 文件：`backtest.risk_free_rate` | 无风险利率（小数形式，如 `0.03` 表示 3%），用于计算夏普/索提诺等指标；优先级：CLI 参数 > `.qmt` 配置文件 > 默认值 `0.03`；由调用方读取后显式传入框架 |
| `backtest.start` / `end` | `.qmt` 配置文件 | 回测时间区间 |
| `backtest.init_capital` | `.qmt` 配置文件 | 初始资金 |
| `data.kline_period` | `.qmt` 配置文件 | K 线周期（`1m` / `5m` / `1d`） |
| `backtest.trigger.type` | `.qmt` 配置文件 | 触发类型（`1m` / `5m` / `1d` / `custom`） |
| `market_callback.post_market_enabled` | `.qmt` 配置文件 | 是否启用盘后回调 |
| `market_callback.post_market_time` | `.qmt` 配置文件 | 盘后回调时间，默认 `15:30:00` |

---

## 九、CLI 入口详解（bt_cli.py）

### 7.1 CLI 流程概览

```
python bt_cli.py run <config.qmt> [参数覆盖]
    │
    ▼
【阶段 1】CLI 层处理          bt_cli.py  cmd_run()
    │  加载 .qmt 配置 → 应用 CLI 参数覆盖（含 --risk-free-rate）→ 写临时配置文件
    │  实例化 CliFrameworkCallbacks（纯 Python）
    │
    ▼
【阶段 2~4】框架执行          framework/core.py  QuantFramework.run(init_data_enabled=..., risk_free_rate=...)
    │  回测结束后计算全量评估指标并写入 summary.csv
    │
    ▼
【阶段 5】CLI 结束收尾        bt_cli.py  _print_result_summary()
       读取最新 backtest_results/ 目录的 summary.csv
       终端打印：总收益率 / 年化收益率 / 最大回撤 / 交易日数 / 交易笔数
```

### 7.2 支持的子命令

| 子命令 | 功能 |
|--------|------|
| `run <config.qmt>` | 运行回测，支持 `--start/--end/--capital/--benchmark/--trigger/--strategy/--init-data/--risk-free-rate` 参数覆盖 |
| `list` | 递归扫描 `strategy/` 目录，列出所有 `.qmt` 策略文件（含周期、区间、初始资金） |
| `results` | 查看 `backtest_results/` 下历史回测结果汇总，支持 `--detail`（展示前5条交易记录）和 `--limit`；列表含夏普比率列 |
| `plot` | 绘制回测结果图表（资产曲线、回撤、收益分布、月度热力图），图表标注区展示完整评估指标；支持 `--save` 保存到文件 |

### 7.3 典型用法

```bash
# 列出所有策略
python bt_cli.py list

# 使用配置文件默认参数运行回测
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt

# 覆盖回测区间和初始资金
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt \
    --start 20240101 --end 20241231 --capital 500000

# 指定无风险利率（用于夏普/索提诺等指标计算，默认 0.03）
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --risk-free-rate 0.025

# 启动时自动下载历史数据
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --init-data

# 详细日志模式（输出所有 INFO 日志）
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt -v

# 查看历史回测结果（含交易明细，含夏普比率列）
python bt_cli.py results --detail

# 绘制最新回测结果图表（弹窗显示，含完整评估指标）
python bt_cli.py plot

# 保存图表到文件（不弹窗）
python bt_cli.py plot --save result.png

# 绘制指定结果目录的图表
python bt_cli.py plot backtest_results/strategy_xxx_20250101_20250703
```

### 7.4 临时配置文件

CLI 使用独立的临时配置文件：

- 临时配置文件路径：`config/temp_bt_cli_config.qmt`

