---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: always
---
# 数据处理专项规范

> 适用场景：涉及时间/日期处理、miniQMT 数据解析、xqshare examples 脚本开发时加载本文件。

---

## 一、时间戳处理规范（强制）

miniQMT 返回的时间索引可能是多种格式，**禁止直接 `pd.to_datetime(int)`**：

| 位数 | 格式 | 解析方式 |
|------|------|---------|
| 8位 | `YYYYMMDD` | `pd.to_datetime(val, format='%Y%m%d')` |
| 14位 | `YYYYMMDDHHMMSS` | `pd.to_datetime(val, format='%Y%m%d%H%M%S')` |
| 13位 | 毫秒时间戳 | `datetime.fromtimestamp(val/1000)`（本地时间，禁用 utc） |

### 1.1 强制规则

1. 转换前必须通过样本值**位数**判断格式，分别用对应方式解析
2. 转换后必须加 `year >= 2000` 合理性校验，过滤掉 NaT 和异常值
3. 写入 `sync_meta.json`（`data_start`/`data_end`）前必须校验年份 >= 2000，否则写 `None`
4. 读取 Parquet 日期时，优先直接扫描文件索引，不依赖 `sync_meta.json`（其中可能有历史脏数据）
5. `storage.save()` 不做格式猜测，要求调用方传入前已转好 `DatetimeIndex`，传错直接报错

### 1.2 xtdata.get_trading_dates() 特别说明

- `xtdata.get_trading_dates()` 实际返回的是 **13位毫秒时间戳**（如 `1704124800000`），不是8位日期
- `_norm_date` 等所有日期解析函数必须兼容13位毫秒时间戳
- 用 `datetime.fromtimestamp(val/1000)` 转换（本地时间，即北京时间）
- **禁止用 `utcfromtimestamp`**（UTC 时间会导致日期少一天）
- 转换后同样需要 `year >= 2000` 校验

### 1.3 集合/列表比较强制规范

对两个集合或列表做交集、差集、包含等比较操作前，必须先确认两边元素的格式（如日期是 `'YYYY-MM-DD'` 还是 `'YYYYMMDD'` 还是整数时间戳），确保格式统一后再比较。

**禁止直接对格式未知或可能不一致的两个集合做 `set` 运算**，否则会产生大量假缺失/假命中。

---

## 二、xqshare examples 连接规范（强制）

`xqshare_src/examples/` 下所有脚本：

- 必须通过 `env_connect.py` 中的 `make_xt()` 工厂函数获取 `XtQuantRemote` 实例
- 禁止在各脚本中直接实例化 `XtQuantRemote` 或手动读取 `.env`
- 使用 `with make_xt() as xt:` 语法管理连接生命周期

### 标准脚本头部模板

```python
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from env_connect import make_xt, print_env_summary

print_env_summary()

with make_xt() as xt:
    # 业务逻辑
    pass
```

---

## 三、Parquet 缓存日期读取规范（强制）

### 3.1 核心原则

**读取已有日期时，必须直接扫描 Parquet 文件索引，禁止依赖 `sync_meta.json` / `sync_meta.parquet`。**

原因：`sync_meta` 中的 `data_start`/`data_end` 是写入时记录的快照，可能存在历史脏数据（如 1970 年时间戳），不能作为完整性判断的依据。

### 3.2 标准读取方式

使用 `data_manager.data_integrity` 模块提供的接口：

```python
from data_manager.data_integrity import get_cached_dates, get_date_range

# 获取已有日期集合（'YYYY-MM-DD' 格式）
actual_dates: set = get_cached_dates(symbol, period)

# 获取数据起止日期
start_date, end_date = get_date_range(symbol, period)
```

**禁止**直接读取 `sync_meta` 中的 `data_start`/`data_end` 来判断数据完整性。

### 3.3 日期格式统一要求

`get_cached_dates()` 返回的集合元素格式统一为 `'YYYY-MM-DD'`。

凡是与此集合做比较的交易日历列表，**必须同样使用 `'YYYY-MM-DD'` 格式**，否则集合运算会产生大量假缺失。

```python
# ✅ 正确：两边格式统一为 'YYYY-MM-DD'
actual_dates = get_cached_dates(symbol, period)   # {'2024-01-02', '2024-01-03', ...}
trading_dates = ['2024-01-02', '2024-01-03', ...]  # 同格式
missing = [d for d in trading_dates if d not in actual_dates]

# ❌ 禁止：格式不一致
actual_dates = get_cached_dates(symbol, period)   # {'2024-01-02', ...}
trading_dates = ['20240102', '20240103', ...]      # YYYYMMDD 格式，会全部误判为缺失
```

---

## 四、缺口段计算规范（强制）

### 4.1 缺口段定义

**缺口段（Gap Segment）**：在已有数据的起止日期范围内，交易日历中存在但本地 Parquet 缓存中缺失的连续交易日区间，表示为 `(gap_start, gap_end)`，格式为 `'YYYYMMDD'`（用于直接传入 `xtdata.download_history_data2`）。

### 4.2 标准计算方式

使用 `data_manager.data_integrity.calc_gap_segments()`：

```python
from data_manager.data_integrity import calc_gap_segments

segments = calc_gap_segments(
    actual_dates=actual_dates,           # set，'YYYY-MM-DD' 格式
    trading_dates_sorted=trading_dates,  # list，已排序，'YYYY-MM-DD' 格式
    range_start='2020-01-01',            # 'YYYY-MM-DD' 格式
    range_end='2024-12-31',              # 'YYYY-MM-DD' 格式
)
# 返回：[('20200103', '20200107'), ('20200210', '20200210'), ...]
# 输出格式为 'YYYYMMDD'，可直接传入 download_history_data2
```

### 4.3 连续性判断规则

两个缺失交易日是否属于同一缺口段，以**交易日历中的相邻关系**为准，而非自然日相邻。

例如：`2024-01-05`（周五）和 `2024-01-08`（周一）在交易日历中相邻，属于同一缺口段。

### 4.4 缺口补充调用规范

补充缺口时，必须使用 `xtdata.download_history_data2`（批量版），禁止使用单股版：

```python
# ✅ 正确：传 stock_list=[symbol] 实现单股下载
xtdata.download_history_data2(
    [symbol],
    period=period_type,
    start_time=seg_start,   # 'YYYYMMDD' 格式
    end_time=seg_end,        # 'YYYYMMDD' 格式
    incrementally=True,
)
```

### 4.5 交易日历获取规范

缺口计算所需的交易日历，必须通过 `DataService._fetch_trading_dates_sorted()` 获取，该方法：
- 从本地 Parquet 缓存 `~/.qmtquant/cache/stock/calendar/trading_calendar.parquet` 读取
- 返回已排序的列表（格式 `'YYYY-MM-DD'`），可直接传入 `calc_gap_segments()`
- 缓存不存在时抛出 `RuntimeError`，提示先执行 `sync --asset stock --sub calendar`

**禁止**在业务代码中自行调用 `xtdata.get_trading_dates()` 获取交易日历。交易日历的远端同步统一通过 `DataService.sync_aux_data()` 或 `CalendarDownloadHandler` 完成，本地消费统一通过 `_fetch_trading_dates_sorted()` 完成。

---

## 五、幽灵标的（Ghost Symbol）过滤规范（强制）

### 5.1 场景描述

在沪深A股成分股列表中，存在一类特殊标的：**`open_date`（上市日期）和 `expire_date`（退市日期）在合约信息中均为空**，但这些标的实际上并非股票（可能是历史遗留的指数、基金、或数据源错误分类的合约）。

已知此类标的共 22 只（截至 2026-05-24 排查），典型特征：

| 代码 | 缓存起始 | 缓存结束 | 行数 |
|------|---------|---------|------|
| 000584.SZ | 1991-01-07 | 2026-05-22 | 8633 |
| 000622.SZ | 1991-01-07 | 2026-05-22 | 8633 |
| 000627.SZ | 1991-01-07 | 2026-05-22 | 8633 |
| 000851.SZ | 1991-01-07 | 2026-05-22 | 8633 |
| 002231.SZ | 1993-05-05 | 2026-05-22 | 8041 |
| 002336.SZ | 1993-05-05 | 2026-05-22 | 8041 |
| 002750.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 300208.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 300280.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 300344.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 300379.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 300391.SZ | 2009-10-30 | 2026-05-22 | 4021 |
| 600190.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 600200.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 600355.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 600387.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 600462.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 600804.SH | 1990-12-19 | 2026-05-22 | 8645 |
| 601989.SH | 1994-02-24 | 2026-05-22 | 7836 |
| 603003.SH | 1994-02-24 | 2026-05-22 | 7836 |
| 603056.SH | 1994-02-24 | 2026-05-22 | 7836 |
| 603388.SH | 2012-05-07 | 2026-05-22 | 3412 |

**判定条件**：`open_date` 为 `None`/空 **且** `expire_date` 为 `None`/`0`/`99999999`（即无退市日）。

> 注意：`open_date` 为 `None` 但 `expire_date` 有值的标的，属于"上市日期缺失"（见 `validate_no_open_date` 需求），与幽灵标的是不同的问题。

### 5.2 影响范围

幽灵标的会在以下环节产生干扰，**必须在各环节添加过滤条件**：

| 环节 | 干扰表现 | 过滤时机 |
|------|---------|---------|
| **数据下载（download）** | 被当作正常股票下载历史数据，浪费资源 | 构建补充任务列表前过滤 |
| **数据同步（sync）** | 被当作正常股票同步到 Parquet，污染缓存 | 构建同步任务列表前过滤 |
| **数据校验（validate）** | 前缺失计算不可信，污染健康统计 | 已由 `no_open_date` 字段单独标记 |
| **策略股票池（strategy）** | 被纳入选股池，产生无效交易信号 | 加载股票池后过滤 |

### 5.3 过滤规范

**判定函数**（在 `data_manager` 或工具模块中统一实现，禁止各处重复写判断逻辑）：

```python
def is_ghost_symbol(instrument_info: dict) -> bool:
    """
    判断是否为幽灵标的（open_date 和 expire_date 均缺失的非股票合约）。
    
    幽灵标的特征：
      - open_date 为 None 或空字符串
      - expire_date 为 None、0 或 99999999（无退市日）
    
    注意：open_date 为 None 但 expire_date 有实际值的标的，
    属于"上市日期缺失"问题，不属于幽灵标的。
    """
    open_date = instrument_info.get('open_date')
    expire_date = instrument_info.get('expire_date')
    
    open_missing = not open_date or open_date in ('', None)
    expire_missing = expire_date in (None, 0, 99999999)
    
    return open_missing and expire_missing
```

**过滤时机**：
- 从板块成分股列表获取 `stock_list` 后，加载合约信息，过滤掉 `is_ghost_symbol == True` 的标的
- 策略加载股票池时，同样过滤

**禁止**：
- 禁止在不同模块各自写 `open_date is None and expire_date in (0, 99999999)` 的判断，必须统一调用 `is_ghost_symbol()`
- 禁止将幽灵标的纳入任何数据下载、同步、策略运算的处理范围

### 5.4 根因说明

这类标的出现在沪深A股成分股列表中的原因尚不明确（可能是 miniQMT 数据源的历史遗留问题或分类错误）。**不要试图修复数据源**，正确做法是在业务代码中过滤掉这类标的。