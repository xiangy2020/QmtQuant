# 框架核心 回测与实盘模式设计说明

> 本文档梳理 `framework/core.py` / `framework/trade.py` 在回测与实盘两种模式下的设计现状、差异点，以及实现实盘所需补充的工作。

---

## 一、现状总览

| 维度 | 现状 |
|------|------|
| 策略接口设计 | ✅ 已统一，天然支持两用 |
| 回测模式 | ✅ 完整实现 |
| 实盘模式 | ❌ 未实现，框架硬编码为回测 |
| `run_mode` 配置项 | ⚠️ 字段存在但未被使用 |

`Config` 从配置文件读取 `run_mode`（默认 `"backtest"`），但 `QuantFramework.run()` 中固定调用 `self._run_backtest()`，没有任何实盘分支：

```python
# framework/core.py - run() 方法
# 固定运行回测模式
self._run_backtest()
```

---

## 二、策略接口层：已统一，可共用

策略文件只需实现以下四个回调函数，框架在特定时机调用，传入统一结构的 `context` 字典：

```python
def init(stock_list, context):          # 启动时调用一次
    pass

def on_bar(context) -> List[Dict]: # 主逻辑，按触发频率反复调用
    return signals

def on_pre_market(context) -> List[Dict]: # 每日盘前（可选）
    return signals

def on_post_market(context) -> List[Dict]: # 每日盘后（可选）
    return signals
```

`context` 字典结构在回测和实盘下完全相同：

```python
context = {
    "__current_time__": {
        "timestamp": int,       # Unix 时间戳
        "datetime": str,        # "YYYY-MM-DD HH:MM:SS"
        "date":     str,        # "YYYY-MM-DD"
        "time":     str,        # "HH:MM:SS"
    },
    "__account__": {
        "account_type": str,
        "account_id":   str,
        "cash":         float,  # 可用资金
        "frozen_cash":  float,  # 冻结资金
        "market_value": float,  # 持仓市值
        "total_asset":  float,  # 总资产
        "benchmark":    str,    # 基准指数代码
    },
    "__positions__": dict,      # 持仓字典，key=股票代码
    "__stock_list__": list,     # 股票池列表
    "__framework__": object,    # QuantFramework 实例
    # 以及各股票的行情数据（key=股票代码）
}
```

策略通过返回标准信号字典列表来下单，不直接调用任何交易 API：

```python
signal = {
    "code":   str,    # 股票代码，如 "000001.SZ"
    "action": str,    # "buy" 或 "sell"
    "price":  float,  # 委托价格
    "volume": int,    # 委托数量（100 的整数倍）
    "reason": str,    # 可选，交易原因
}
```

**结论：策略文件本身写一套即可，回测和实盘共用。**

---

## 三、各层差异详解

### 3.1 账户初始化层

**回测（已实现）**：`init_trader_and_account()` 固定调用 `_init_virtual_account()`，在内存中创建虚拟账户：

```python
def init_trader_and_account(self):
    # 固定为回测模式，只进行虚拟账户初始化
    self._init_virtual_account()

def _init_virtual_account(self):
    self.trade_mgr.assets = {
        "cash":         init_capital,   # 来自配置文件
        "frozen_cash":  0.0,
        "market_value": 0.0,
        "total_asset":  init_capital,
        ...
    }
    self.trade_mgr.positions = {}  # 初始持仓为空
```

**实盘（待实现）**：需要连接 QMT 客户端，查询真实账户资金和持仓：

```python
# 待实现
def _init_real_account(self):
    self.trader = XtQuantTrader(self.qmt_path, self.config.session_id)
    self.account = StockAccount(self.config.account_id, "STOCK")
    self.trader.connect()
    # 查询真实资金和持仓，写入 trade_mgr.assets / trade_mgr.positions
```

---

### 3.2 行情驱动层

**回测**：`_run_backtest()` 用 `for` 循环遍历历史时间戳，逐根 bar 调用 `on_bar`：

```
预下载历史数据
  └─ for 每个交易日
       └─ for 每个时间戳
            └─ 构建 context → 调用 on_bar(context)
```

**实盘（待实现）**：需要订阅实时行情，在行情回调中触发策略：

```
订阅实时行情（subscribe_quote）
  └─ 行情推送回调（on_data）
       └─ 构建 context → 调用 on_bar(context)
```

| 维度 | 回测 | 实盘 |
|------|------|------|
| 数据来源 | `xtdata.download_history_data2()` 预下载 | 实时订阅推送 |
| 驱动方式 | `for` 循环遍历历史时间戳 | 行情回调触发 |
| 时间控制 | 框架完全掌控，可快进 | 必须等真实时钟 |
| 数据完整性 | 每根 bar 结束后触发，数据完整 | 推送频率约 3 秒一次，bar 未收完就触发 |
| 历史 bar 过滤 | 不存在 | QMT 启动时回放当日历史 bar，需过滤（`bar_date != 今日系统日期`） |
| 缺数据处理 | 直接跳过 | 需容错，行情可能中断 |

---

### 3.3 下单执行层

`TradeManager.place_order()` 已有模式分支，但实盘分支是空实现：

```python
# framework/trade.py
def place_order(self, signal: Dict):
    if self.config.run_mode == "live":
        self._place_order_live(signal)      # ← 空实现
    elif self.config.run_mode == "simulate":
        self._place_order_simulate(signal)  # ← 简单模拟
    else:
        self._place_order_backtest(signal)  # ← 完整实现

def _place_order_live(self, signal: Dict):
    # 调用miniQMT的交易接口
    print(f"实盘下单信号: {signal}")
    # 这里需要调用实际的交易接口   ← 待实现
```

**回测下单假设**：

```python
def _place_order_backtest(self, signal):
    "traded_volume": signal["volume"],          # 假设全部成交
    "order_status": xtconstant.ORDER_SUCCEEDED, # 假设立即成交
```

**实盘下单需要处理的真实流程**：

```
发出委托 → 等待交易所确认 → 可能部分成交 → 可能排队等待 → 可能废单/拒单
```

| 场景 | 回测处理 | 实盘需要额外处理 |
|------|---------|----------------|
| 成交确认 | 假设立即全部成交 | 异步回调 `on_stock_trade` 后更新 |
| 部分成交 | 不存在 | 需跟踪 `traded_volume` vs `order_volume` |
| 废单/拒单 | 不存在 | 需处理风控拒绝、余额不足等错误回调 |
| 重复下单 | 不存在 | 需 `order_id` 去重，防止网络重试导致重复委托 |
| 涨跌停无法成交 | 假设成交 | 委托排队，需检查委托状态 |
| 资金冻结 | 无 | 委托发出后资金冻结，需区分可用/冻结 |

---

### 3.4 账户状态同步层

| 维度 | 回测 | 实盘 |
|------|------|------|
| 持仓来源 | `trade_mgr.positions`（内存字典） | 每次需查询券商真实持仓 |
| 资金来源 | `trade_mgr.assets["cash"]`（内存） | 需查询真实可用资金 |
| 持仓更新时机 | 成交后立即同步（同步调用） | 异步回调 `on_stock_trade` 后更新 |
| T+1 限制 | 框架自行模拟 | 券商系统强制执行，`can_use_volume` 字段 |
| 策略重启恢复 | 无需恢复，重新跑历史 | 必须从真实持仓重建策略内存状态 |

---

### 3.5 时间与调度层

| 场景 | 回测 | 实盘 |
|------|------|------|
| 非交易日 | 数据中没有，自动跳过 | 程序仍在运行，需判断是否交易日 |
| 盘前历史 bar 回放 | 不存在 | QMT 启动时会回放当日历史 bar，需过滤 |
| 盘后回调触发 | 在每日最后一根 bar 后触发 | 需注册定时任务，依赖系统时钟 |
| 网络中断 | 不存在 | 行情/交易接口可能断线，需重连机制 |
| 程序崩溃恢复 | 重新回测即可 | 需从真实持仓重建内存状态 |

---

## 四、实现实盘所需补充的工作

框架层需要在以下 4 个位置补充实盘实现，**策略文件本身不需要改动**：

```
QuantFramework.run()
  ├── if run_mode == 'backtest' → self._run_backtest()    ✅ 已实现
  └── if run_mode == 'live'    → self._run_live()         ❌ 待实现

QuantFramework.init_trader_and_account()
  ├── 回测 → self._init_virtual_account()                 ✅ 已实现
  └── 实盘 → self._init_real_account()                    ❌ 待实现

TradeManager._place_order_live(signal)
  └── 调用 xtquant 真实下单接口                            ❌ 空实现

TradeManager（账户状态同步）
  └── 异步回调处理：on_stock_trade / on_order_error 等     ❌ 待完善
```

### 4.1 `_run_live()` 核心逻辑框架

```python
def _run_live(self):
    """实盘模式（待实现）"""
    stock_codes = self.get_stock_list()

    # 1. 订阅实时行情
    xtdata.subscribe_quote(stock_codes, period=self.trigger.get_data_period(),
                           callback=self._on_market_data)

    # 2. 注册盘前/盘后定时任务
    if pre_market_enabled:
        xtdata.run_time('on_pre_market', '1nDay', pre_market_time,
                        callback=self._on_pre_market)
    if post_market_enabled:
        xtdata.run_time('on_post_market', '1nDay', post_market_time,
                        callback=self._on_post_market)

    # 3. 阻塞等待行情推送
    xtdata.run()

def _on_market_data(self, data):
    """行情推送回调"""
    # 过滤历史 bar（QMT 启动时回放）
    bar_date = ...
    if bar_date != today:
        return

    # 构建与回测相同结构的 context
    context = self._build_context(data)

    # 调用策略主逻辑（与回测完全相同的调用方式）
    signals = self.strategy_module.on_bar(context)
    if signals:
        self.trade_mgr.process_signals(signals)
```

### 4.2 `_place_order_live()` 核心逻辑框架

```python
def _place_order_live(self, signal: Dict):
    """实盘下单（待实现）"""
    order_type = xtconstant.STOCK_BUY if signal["action"] == "buy" \
                 else xtconstant.STOCK_SELL

    # 调用 xtquant 异步下单
    order_id = self.framework.trader.order_stock_async(
        account=self.framework.account,
        stock_code=signal["code"],
        order_type=order_type,
        order_volume=signal["volume"],
        price_type=xtconstant.FIX_PRICE,
        price=signal["price"],
        strategy_name="framework",
        order_remark=signal.get("reason", "")
    )

    # 记录委托，等待异步回调确认
    self.orders[order_id] = {
        "stock_code": signal["code"],
        "order_volume": signal["volume"],
        "traded_volume": 0,          # 等待回调更新
        "order_status": "pending",
        ...
    }
```

---

## 五、总结

```
回测 = 历史数据回放 + 虚拟撮合 + 同步执行
实盘 = 实时行情订阅 + 真实委托 + 异步确认 + 状态恢复 + 容错处理
```

策略逻辑层（`on_bar` 返回信号）可以完全共用，框架需要在以下 4 个层面分别实现实盘版本：

| 层 | 回测 | 实盘 |
|----|------|------|
| 账户初始化 | 内存虚拟账户 | 连接 QMT，查询真实账户 |
| 行情驱动 | 历史数据 `for` 循环 | 实时订阅回调 |
| 下单执行 | 假设立即全部成交 | `xtquant` 异步委托 + 回调确认 |
| 账户状态 | 内存同步更新 | 异步回调 + 真实持仓查询 |
