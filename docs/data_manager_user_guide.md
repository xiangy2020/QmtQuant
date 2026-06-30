# data_manager user guide

## 概述

`data_manager` 是项目的本地数据管理模块，负责将 Windows 端 miniQMT 的行情数据同步到 Mac 本地，并提供统一的查询接口供策略、回测、数据查看器等模块使用。

**核心数据流：**

```
[行情源] → miniQMT 落盘 Windows .DAT
              ↓ 补充数据触发
         Windows xtdata.download_history_data()
              ↓
         Windows xtdata.get_market_data_ex()
              ↓ xqshare 网络传输
         Mac data_manager 写入本地 Parquet
              ↓ 日常使用
         策略 / 回测 / 查看器 直接读取（毫秒级）
```

**关键原则：Mac 端缓存是 Windows 数据的镜像副本，不是独立数据源。数据必须先在 Windows 端落盘，才能同步到 Mac。**

---

## 安装依赖

```bash
pip install pyarrow>=12.0
```

---

## 模块结构

```
data_manager/
├── __init__.py          # 统一导出入口
├── storage.py           # 存储引擎（Parquet 读写）
├── sync_manager.py      # 同步状态元数据管理
├── sync_pipeline.py     # 数据同步框架（Source/Sink/Pipeline）
├── data_integrity.py    # 数据完整性检测（缺口计算）
├── asset_types.py       # 品类体系定义
└── migration.py         # 数据迁移工具
```

**本地缓存目录结构：**

```
~/.qmtquant/cache/
├── stock/                                    ← 股票品类
│   ├── kline/                                ← K线行情
│   │   ├── 1d/
│   │   │   ├── SH/
│   │   │   │   ├── 600000.parquet   ← 600000.SH 日线
│   │   │   │   └── 601318.parquet
│   │   │   └── SZ/
│   │   │       └── 000001.parquet   ← 000001.SZ 日线
│   │   ├── 1m/
│   │   │   └── SH/
│   │   │       └── 600000.parquet
│   │   ├── 5m/
│   │   └── sync_meta.parquet             ← 同步状态元数据
│   ├── calendar/
│   │   └── trading_calendar.parquet      ← 交易日历
│   └── instrument/
│       └── instrument_detail.parquet     ← 合约基础信息
├── industry/                                 ← 行业概念品类
│   ├── sector_list/
│   │   └── sector_list.parquet           ← 板块列表
│   └── members/
│       └── {sector_name}.parquet         ← 各板块成分股
└── pools/                                    ← 自定义股票池
    └── {pool_name}.parquet
```

---

## 一、日常使用：查询 K 线数据

这是最常用的接口，**策略和回测代码应统一使用此接口**，无需关心数据来源。

```python
from data_service import DataService

service = DataService()

# ── 单只股票查询 ──────────────────────────────────────────────────
df = service.query_kline('600000.SH', '1d')
# 从本地 Parquet 缓存直接读取（毫秒级）
# 若本地无缓存则返回空 DataFrame，不会自动 fallback 到远程

# 指定日期范围（支持 'YYYYMMDD' 或 'YYYY-MM-DD' 格式）
df = service.query_kline('600000.SH', '1d', start_date='20240101', end_date='20241231')

# ── 多只股票查询 ──────────────────────────────────────────────────
for symbol in ['600000.SH', '000001.SZ', '601318.SH']:
    df = service.query_kline(symbol, '1d', start_date='20240101')
    if not df.empty:
        print(f"{symbol}: {len(df)} 条")
```

---

## 二、补充数据后自动同步（已内置，无需手动调用）

执行主界面的「补充历史数据」后，同步会**自动触发**，无需额外操作。

补充数据日志中会出现：
```
补充 600000.SH 数据成功: 获取 250 行, 6 列, 时间跨度: 2024-01-02 至 2024-12-31
✓ 已同步到本地缓存 [600000.SH 1d]，共 250 条记录
```

如需在自定义脚本中手动触发同步（例如批量导入历史数据），可直接调用：

```python
from data_manager import sync_from_windows
import pandas as pd

# df 必须是已从 Windows 端读取的 DataFrame（DatetimeIndex）
success = sync_from_windows('600000.SH', '1d', df)
print(f"同步{'成功' if success else '失败'}")

# 查询同步状态
from data_manager import get_sync_status
status = get_sync_status('600000.SH', '1d')
if status:
    print(f"最后同步：{status['last_sync']}")
    print(f"数据范围：{status['data_start']} ~ {status['data_end']}")
    print(f"记录数：{status['record_count']}")
```

---

## 三、缺失补充（gap_download）

### 功能描述

`gap_download` 用于检测本地 Parquet 缓存中已有数据的**缺口段**（即交易日历中存在但本地缺失的交易日），并自动从 miniQMT 补充这些缺口，而无需重新下载全量数据。

**适用场景：**
- 历史数据中间有断档（如节假日前后补充不完整）
- 网络中断导致部分日期数据缺失
- 增量同步后发现有遗漏

### 通过界面操作

打开「本地数据管理模块」→「缺失补充」标签页：

1. 选择需要检测的股票列表和周期
2. 点击「检测缺口」，系统自动扫描 Parquet 缓存与交易日历的差异
3. 确认缺口列表后，点击「开始补充」

日志面板会显示每个缺口段的补充进度：
```
[600000.SH] 检测到 3 个缺口段
  缺口1: 20240105 ~ 20240108 (3个交易日)
  缺口2: 20240215 ~ 20240215 (1个交易日)
  缺口3: 20240520 ~ 20240522 (3个交易日)
正在补充缺口1: 20240105 ~ 20240108 ...
✓ 缺口1 补充完成
...
[600000.SH] 全部缺口补充完成
```

### 通过 DataService 调用

```python
from data_service import DataService

service = DataService()

# 定义回调
class MyCallbacks:
    def on_progress(self, done, total):
        print(f"进度: {done}/{total}")
    def on_log(self, msg):
        print(f"[LOG] {msg}")
    def on_error(self, err):
        print(f"[ERR] {err}")
    def on_done(self, result):
        print(f"完成: {result}")

result = service.gap_download(
    params={
        'stock_list': ['600000.SH', '000001.SZ'],
        'period_type': '1d',
    },
    callbacks=MyCallbacks(),
)

# result 结构：
# {
#   'success': True,
#   'message': '补充完成',
#   'interrupted': False,    # 是否被中途停止
#   'processed': 2,          # 处理的股票数
#   'has_gap': 1,            # 有缺口的股票数
#   'no_gap': 1,             # 无缺口的股票数
#   'total_segments': 3,     # 总缺口段数
#   'done_segments': 3,      # 已补充的缺口段数
# }
```

### 直接使用 data_integrity 模块（高级用法）

```python
from data_manager.data_integrity import get_cached_dates, get_date_range, calc_gap_segments

# 获取已有日期集合（'YYYY-MM-DD' 格式）
actual_dates = get_cached_dates('600000.SH', '1d')
print(f"本地已有 {len(actual_dates)} 个交易日")

# 获取数据起止日期
start_date, end_date = get_date_range('600000.SH', '1d')
print(f"数据范围: {start_date} ~ {end_date}")

# 计算缺口段（需要先准备交易日历，格式为 'YYYY-MM-DD' 的有序列表）
trading_dates = [...]  # 通过 DataService._fetch_trading_dates_sorted() 获取（从本地 Parquet 缓存读取）
segments = calc_gap_segments(
    actual_dates=actual_dates,
    trading_dates_sorted=trading_dates,
    range_start=start_date,
    range_end=end_date,
)
# 返回：[('20240105', '20240108'), ('20240215', '20240215'), ...]
# 输出格式为 'YYYYMMDD'，可直接传入 xtdata.download_history_data2
print(f"检测到 {len(segments)} 个缺口段: {segments}")
```

> ⚠️ **注意**：`get_cached_dates()` 返回的日期格式为 `'YYYY-MM-DD'`，与之比较的交易日历列表**必须使用相同格式**，否则集合运算会产生大量假缺失。禁止直接依赖 `sync_meta.json` 中的 `data_start`/`data_end` 判断数据完整性。

---

## 四、直接操作存储引擎（高级用法）

```python
from data_manager import Storage

storage = Storage()  # 使用默认缓存目录 ~/.qmtquant/cache/stock/
# 也可指定自定义目录：Storage(cache_root='/path/to/cache')

# 查看已缓存的周期
periods = storage.list_periods()
print(periods)  # ['1d', '1m', '5m']

# 查看某周期下所有已缓存股票
symbols = storage.list_symbols('1d')
print(symbols[:5])  # ['000001.SZ', '000002.SZ', ..., '600000.SH']

# 获取单只股票的缓存详情
info = storage.get_info('600000.SH', '1d')
# {
#   'symbol': '600000.SH',
#   'period': '1d',
#   'start_date': '2020-01-02',
#   'end_date': '2024-12-31',
#   'record_count': 1200,
#   'file_size_mb': 0.0842,
#   'last_modified': datetime(2025, 5, 19, 11, 17, 0)
# }

# 判断缓存是否存在
if storage.exists('600000.SH', '1d'):
    print("缓存存在")

# 手动写入数据（增量合并，自动去重）
storage.save('600000.SH', '1d', df)

# 读取数据
df = storage.load('600000.SH', '1d', start_date='20240101', end_date='20241231')

# 删除单只股票的缓存
storage.delete('600000.SH', '1d')
```

---

## 五、缓存管理


### 4.2 通过代码操作

```python
from data_manager import get_statistics, validate_cache, clear_all
from data_manager.cache_manager import clear_symbol

# 查看缓存统计
stats = get_statistics()
print(f"总缓存：{stats['total_size_mb']:.1f} MB")
print(f"数据范围：{stats['global_start_date']} ~ {stats['global_end_date']}")
for period, info in stats['periods'].items():
    print(f"  {period}：{info['symbol_count']} 只，{info['size_mb']} MB")
print(f"是否超过 5GB 警告阈值：{stats['is_over_threshold']}")

# 校验单只股票缓存文件完整性
result = validate_cache('600000.SH', '1d')
print(f"文件存在：{result['exists']}")
print(f"可正常读取：{result['readable']}")
print(f"记录数：{result['record_count']}")

# 清空所有缓存
result = clear_all()
print(f"已删除 {result['deleted_files']} 个文件，释放 {result['freed_mb']:.1f} MB")

# 清除单只股票的缓存（所有周期）
result = clear_symbol('600000.SH')

# 清除单只股票指定周期的缓存
result = clear_symbol('600000.SH', period='1d')
```

---

## 七、注意事项

1. **数据权威来源是 Windows**：Mac 缓存只是镜像，不要直接修改 Parquet 文件
2. **只缓存不复权数据**：复权数据通过 QMT API 实时计算，不预存
3. **Tick 数据不缓存**：Tick 数据仍走原有远程读取流程
4. **同步失败不影响补充数据**：即使 Mac 缓存写入失败，Windows 端数据不受影响
5. **缓存目录**：`~/.qmtquant/cache/`（跨平台，Mac/Windows 均适用），K线数据存储于 `~/.qmtquant/cache/stock/kline/`
6. **禁止依赖 sync_meta 判断完整性**：`sync_meta.json` 中的 `data_start`/`data_end` 是写入时的快照，可能存在历史脏数据（如 1970 年时间戳）。判断数据完整性必须通过 `data_integrity.get_cached_dates()` 直接扫描 Parquet 文件索引
7. **缺口计算的日期格式必须统一**：`get_cached_dates()` 返回 `'YYYY-MM-DD'` 格式，与之比较的交易日历列表必须使用相同格式，禁止混用 `'YYYYMMDD'` 或整数时间戳，否则会产生大量假缺失
8. **交易日历获取统一入口**：缺口计算所需的交易日历必须通过 `DataService._fetch_trading_dates_sorted()` 获取（内部从本地 Parquet 缓存 `~/.qmtquant/cache/stock/calendar/trading_calendar.parquet` 读取），禁止在业务代码中自行调用 `xtdata.get_trading_dates()` 或自行解析返回值。必须先通过 `sync --asset stock --sub calendar` 将交易日历同步到本地缓存后方可使用

---

## 八、CLI 命令行调用

`dm_cli.py` 是数据模块的命令行入口，适用于**定时任务、脚本自动化、开发调试**等场景。

### 8.1 命令总览

```
python dm_cli.py <命令> [选项]
```

| 命令 | 说明 |
|------|------|
| `stats` | 查看本地缓存统计信息 |
| `validate` | 对板块/股票执行全面数据健康检查 |
| `clear` | 清空缓存（全部、指定股票、日期异常数据或上市日期缺失标的） |
| `sync` | miniQMT → Parquet 数据同步（支持全量/智能模式） |
| `download` | 全量/增量/缺口/智能数据下载（下载到 miniQMT 本地） |
| `scan-gaps` | 扫描数据缺口（只检测，不补充） |
| `schedule` | 定时调度数据下载（持续运行 / 立即执行一次） |

全局选项：
- `-v` / `--verbose`：输出详细日志（DEBUG 级别）
- `--list`：展示已启用品类体系表格后退出

### 8.2 品类体系（--asset / --sub）

所有操作类子命令均支持通过 `--asset` 和 `--sub` 指定操作对象的品类：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--asset` | 一级品类，如 `stock`、`industry` | `stock` |
| `--sub` | 二级子类，如 `kline`、`calendar`、`instrument` | `kline` |

查看完整品类体系：
```bash
python dm_cli.py --list
```

### 8.3 操作对象指定（--sector 与 --symbols）

对于 `stock/kline` 子类，必须通过以下**二选一**方式指定操作对象：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--sector 板块名` | 通过板块名称指定（板块需预先创建） | `--sector 沪深A股` |
| `--symbols 代码列表` | 直接指定股票代码，多个用英文逗号分隔 | `--symbols 000001.SZ,600000.SH` |

> **注意**：`--sector` 和 `--symbols` 互斥，不能同时使用。

### 8.4 各命令详解

#### `stats` — 缓存统计

```bash
# 查看整体缓存统计
python dm_cli.py stats

# 查看 stock/kline 数据明细（默认展示前 50 条）
python dm_cli.py stats --asset stock --sub kline

# 查看指定股票代码的 kline 明细（无需创建板块）
python dm_cli.py stats --asset stock --sub kline --symbols 000001.SZ,600000.SH

# 按周期过滤 kline 明细
python dm_cli.py stats --asset stock --sub kline --period 1d
```

参数：
- `--asset`：一级品类，默认 `stock`
- `--sub`：二级子类，默认 `kline`
- `--symbols`：股票代码列表，多个用英文逗号分隔（仅 kline 子类有效，不指定则展示全量）
- `--period`：过滤 kline 子类的周期，如 `1d`
- `--limit`：展示条数，`0` 或 `-1` 表示全量（默认 50）

---

#### `validate` — 全面数据健康检查

对板块或指定股票执行全面数据健康检查，检测以下问题并给出修复建议：

| 检测维度 | 说明 |
|---------|------|
| 无缓存 | 本地 Parquet 文件不存在 |
| 字段不完整 | required_fields 中有列缺失 |
| 类型异常 | 列类型或索引类型不符合预期 |
| 前缺失 | 缓存起始日期晚于上市日期（T1）的情况 |
| 后缺失 | 缓存最新日期早于最近交易日（T2）的情况 |
| 中间缺口 | 缓存范围内存在连续缺失的交易日段 |
| 日期异常 | 存在早于 A 股开市日（1990-12-19）的脏数据行 |
| 上市日期缺失 | 合约信息中 `open_date` 为 `None`，前缺失检测不可信 |

> **上市日期缺失说明**：当合约信息中 `open_date` 为 `None` 时，系统无法确定前缺失的起点，因此**跳过前缺失检测**（不会误报），并将该标的标记为 `no_open_date`。此类标的建议删除缓存后重新同步。

```bash
# 通过板块名称检查
python dm_cli.py validate --asset stock --sub kline --sector 沪深A股 --period 1d

# 直接指定股票代码检查（无需创建板块）
python dm_cli.py validate --symbols 000001.SZ,600000.SH --period 1d

# 显示每只问题股票的详细信息
python dm_cli.py validate --sector 沪深A股 --period 1d --detail

# 显示详细信息 + 各检测维度的判断明细（T1/T2 推导过程等）
python dm_cli.py validate --sector 沪深A股 --period 1d --detail -v

# 省略 --asset/--sub（默认 stock/kline）
python dm_cli.py validate --sector 沪深A股 --period 1d
```

参数：
- `--asset`：一级品类，默认 `stock`
- `--sub`：二级子类，默认 `kline`
- `--sector`：板块名称（与 `--symbols` 互斥，kline 子类时二选一必填）
- `--symbols`：股票代码列表，多个用英文逗号分隔（与 `--sector` 互斥）
- `--period`（必填）：数据周期，如 `1d`
- `--detail`：显示每只问题股票的详细信息
- `-v` / `--verbose`：配合 `--detail` 使用，展示各检测维度的判断明细（T1/T2 推导过程、缺口扫描区间等）

**汇总输出示例：**
```
  ──────────────────────────────────────────────────
  校验汇总（1d）：
    总扫描：5000 只
    ✅ 完全健康：4800 只
    ⬜ 无缓存：10 只
    🔴 字段不完整：0 只
    🟠 类型异常：0 只
    🟡 前缺失：50 只
    🟡 后缺失：30 只
    🟡 中间缺口：100 只
    🔴 日期异常：5 只
    ⚠️  上市日期缺失：5 只
  ──────────────────────────────────────────────────
```

---

#### `clear` — 清空缓存

支持四种清理模式（四选一，必填）：

| 模式参数 | 说明 |
|---------|------|
| `--all` | 清空全部缓存（需输入 yes 二次确认） |
| `--symbol 代码` | 清除指定单只股票的缓存 |
| `--date-anomaly` | 精准行级清理：删除早于 A 股开市日（1990-12-19）的脏数据行，**保留正常数据** |
| `--no-open-date` | 整个文件删除：删除上市日期缺失标的的整个缓存文件，**需重新同步** |

```bash
# 清除单只股票指定周期的缓存
python dm_cli.py clear --symbol 600000.SH --period 1d

# 清除单只股票所有周期的缓存
python dm_cli.py clear --symbol 600000.SH

# 清空全部缓存（需输入 yes 二次确认）
python dm_cli.py clear --all

# 精准清理日期异常数据（按板块）
python dm_cli.py clear --date-anomaly --sector 沪深A股 --period 1d

# 精准清理日期异常数据（指定代码）
python dm_cli.py clear --date-anomaly --symbols 000001.SZ,600000.SH --period 1d

# 精准清理日期异常数据（全量缓存，跳过确认）
python dm_cli.py clear --date-anomaly --yes

# 删除上市日期缺失标的的缓存文件（按板块）
python dm_cli.py clear --no-open-date --sector 沪深A股 --period 1d

# 删除上市日期缺失标的的缓存文件（指定代码）
python dm_cli.py clear --no-open-date --symbols 000584.SZ --period 1d

# 删除上市日期缺失标的的缓存文件（全量扫描，跳过确认）
python dm_cli.py clear --no-open-date --yes
```

参数（四选一，必填）：
- `--all`：清空全部缓存
- `--symbol 代码`：清除指定股票的缓存
- `--date-anomaly`：精准行级清理日期异常数据
- `--no-open-date`：整个文件删除上市日期缺失标的的缓存

可选：
- `--period`：指定周期；不指定则处理所有周期
- `--sector`：板块名称（配合 `--date-anomaly` / `--no-open-date` 使用，与 `--symbols` 互斥）
- `--symbols`：股票代码列表，多个用英文逗号分隔（配合 `--date-anomaly` / `--no-open-date` 使用，与 `--sector` 互斥）
- `--yes` / `-y`：跳过二次确认直接执行（用于脚本自动化）

> **`--date-anomaly` vs `--no-open-date` 的区别**：
> - `--date-anomaly`：**行级清理**，只删除异常行（早于 1990-12-19 的数据），正常数据保留，文件继续存在
> - `--no-open-date`：**整个文件删除**，删除整个 Parquet 文件，需要重新执行 `sync` 才能恢复数据

---

#### `sync` — 数据同步

将 miniQMT 本地缓存同步到 Parquet（不触发下载，只读取已有数据）。支持 `full`（全量覆盖写）和 `smart`（先 validate 再精准同步缺失部分）两种模式。

```bash
# 全量同步（默认）
python dm_cli.py sync --asset stock --sub kline --sector 沪深A股 --period 1d

# 直接指定股票代码同步（无需创建板块）
python dm_cli.py sync --symbols 000001.SZ,600000.SH --period 1d

# 智能同步（先 validate 扫描，再精准同步缺失部分）
python dm_cli.py sync --asset stock --sub kline --sector 沪深A股 --period 1d --mode smart

# 智能同步（跳过确认直接执行）
python dm_cli.py sync --sector 沪深A股 --period 1d --mode smart --yes

# 同步辅助数据（交易日历 + 合约信息）
python dm_cli.py sync --asset stock --sub calendar,instrument

# 同步行业概念数据
python dm_cli.py sync --asset industry
```

参数：
- `--asset`：一级品类，多个用逗号分隔，不指定则同步所有已启用品类
- `--sub`：二级子类，多个用逗号分隔，不指定则同步该品类所有子类
- `--sector`：板块名称（同步 kline 子类时与 `--symbols` 二选一；同步 instrument 子类时可选）
- `--symbols`：股票代码列表，多个用英文逗号分隔（与 `--sector` 互斥）
- `--period`：数据周期，多个用逗号分隔，如 `1d,1m`（同步 kline 子类时必填）
- `--start`：起始日期 `YYYYMMDD`，默认 `19900101`（仅 kline full 模式）
- `--end`：结束日期 `YYYYMMDD`，默认最新（仅 kline）
- `--mode`：同步模式，`full`（默认）或 `smart`
- `--yes` / `-y`：smart 模式下跳过确认直接执行

---

#### `download` — 数据下载

触发 miniQMT 从行情源下载数据到本地（需要 xqshare 连接）。支持四种模式：

| 模式 | 说明 |
|------|------|
| `incremental`（默认） | 增量：从 miniQMT 本地最后一条数据往后补充 |
| `full` | 全量：强制重新下载指定日期范围内的全部数据（需指定 `--start`） |
| `gap` | 缺口：扫描 Parquet 缓存缺口后精准下载 |
| `smart` | 智能：自动 validate → 分层 → 精准下载（一键修复所有问题） |

```bash
# 增量下载（默认）
python dm_cli.py download --asset stock --sub kline --sector 沪深A股 --period 1d

# 直接指定股票代码下载（无需创建板块）
python dm_cli.py download --symbols 000001.SZ,600000.SH --period 1d

# 全量下载指定日期范围
python dm_cli.py download --sector 沪深A股 --period 1d --mode full --start 20240101 --end 20241231

# 缺口下载
python dm_cli.py download --sector 沪深A股 --period 1d --mode gap

# 智能下载（一键修复所有问题）
python dm_cli.py download --sector 沪深A股 --period 1d --mode smart

# 智能下载（跳过确认）
python dm_cli.py download --sector 沪深A股 --period 1d --mode smart --yes
```

参数：
- `--asset`：一级品类，默认 `stock`
- `--sub`：二级子类，默认 `kline`
- `--sector`：板块名称（与 `--symbols` 互斥，kline 子类时二选一必填）
- `--symbols`：股票代码列表，多个用英文逗号分隔（与 `--sector` 互斥）
- `--period`（必填）：数据周期，多个用逗号分隔，如 `1d,1m`
- `--mode`：下载模式，`incremental`（默认）/ `full` / `gap` / `smart`
- `--start`：起始日期（full 模式必填；smart 模式下作为无 open_date 标的的默认起始日期）
- `--end`：结束日期，默认最新（仅 full 模式有效）
- `--yes` / `-y`：smart 模式下跳过确认提示，直接执行

---

#### `scan-gaps` — 扫描缺口

扫描股票数据缺口，**只检测，不补充**，适合在补充前先确认缺口情况。

```bash
# 基础扫描（只显示汇总）
python dm_cli.py scan-gaps --sector 沪深A股 --period 1d

# 显示每只股票的缺口明细
python dm_cli.py scan-gaps --sector 沪深A股 --period 1d --detail
```

参数：
- `--sector`：板块名称（kline 子类时必填）
- `--period`（必填）：数据周期，多个用逗号分隔
- `--detail`：显示每只股票的缺口段明细

---

#### `schedule` — 定时调度

启动独立后端调度服务，在每个工作日的指定时间自动执行数据下载（仅交易日触发）。支持持续运行和一次性执行两种模式。

```bash
# 持续调度（每个工作日 15:30 执行，Ctrl+C 停止）
python dm_cli.py schedule --sector 沪深300 --period 1d --time 15:30

# 多周期调度
python dm_cli.py schedule --sector 沪深300 --period 1d,1m --time 15:30

# 立即执行一次后退出（不进入持续调度模式）
python dm_cli.py schedule --sector 沪深300 --period 1d --run-now

# 立即执行一次，然后继续保持调度运行
python dm_cli.py schedule --sector 沪深300 --period 1d --time 15:30 --run-now --no-exit

# 指定补充模式（缺口补充）
python dm_cli.py schedule --sector 沪深300 --period 1d --mode gap
```

参数：
- `--sector`（必填）：板块名称
- `--period`（必填）：数据周期，多个用逗号分隔，如 `1d,1m`
- `--time`：每日执行时间，格式 `HH:MM`，默认 `15:30`
- `--mode`：补充模式，`incremental`（默认）/ `full` / `gap`
- `--asset`：一级品类，默认 `stock`
- `--sub`：二级子类，默认 `kline`
- `--run-now`：立即执行一次补充任务
- `--no-exit`：与 `--run-now` 配合使用，执行后继续保持调度运行

> **调度逻辑**：
> - 仅在周一至周五触发，执行时自动检查当日是否为交易日，非交易日自动跳过
> - 多周期按顺序串行执行，前一周期完成后再执行下一个
> - 单次执行失败不停止调度服务，下次定时继续尝试
> - 按 `Ctrl+C` 后优雅停止（等待当前任务完成后退出）

### 8.5 典型工作流

**首次初始化（从零开始）：**

```bash
# 1. 同步辅助数据（交易日历 + 合约信息）
python dm_cli.py sync --asset stock --sub calendar,instrument

# 2. 下载历史数据到 miniQMT 本地
python dm_cli.py download --sector 沪深A股 --period 1d --mode full --start 20200101

# 3. 将 miniQMT 数据同步到 Parquet 缓存
python dm_cli.py sync --sector 沪深A股 --period 1d
```

**日常增量更新（定时任务）：**

```bash
# 增量下载 + 同步（每日收盘后执行）
python dm_cli.py download --sector 沪深A股 --period 1d --mode smart
python dm_cli.py sync --sector 沪深A股 --period 1d --mode smart --yes
```

**自动定时调度（无人值守）：**

```bash
# 启动定时调度服务，每个工作日 15:30 自动执行增量补充（Ctrl+C 停止）
python dm_cli.py schedule --sector 沪深A股 --period 1d --time 15:30

# 多周期定时调度
python dm_cli.py schedule --sector 沪深A股 --period 1d,1m --time 15:30

# 先立即执行一次，然后继续定时调度
python dm_cli.py schedule --sector 沪深A股 --period 1d --time 15:30 --run-now --no-exit
```

**一键智能修复（发现数据问题后）：**

```bash
# 先 validate 确认问题
python dm_cli.py validate --sector 沪深A股 --period 1d --detail

# 智能下载（自动修复 miniQMT 本地缺失）
python dm_cli.py download --sector 沪深A股 --period 1d --mode smart

# 智能同步（自动修复 Parquet 缓存缺失）
python dm_cli.py sync --sector 沪深A股 --period 1d --mode smart
```

**对单只/少量股票操作（无需创建板块）：**

```bash
# 直接指定代码进行健康检查
python dm_cli.py validate --symbols 000001.SZ,600000.SH --period 1d

# 直接指定代码进行智能下载
python dm_cli.py download --symbols 000001.SZ --period 1d --mode smart

# 直接指定代码进行同步
python dm_cli.py sync --symbols 000001.SZ,600000.SH --period 1d
```

**处理日期异常数据（精准行级清理）：**

```bash
# 先 validate 确认日期异常情况
python dm_cli.py validate --sector 沪深A股 --period 1d --detail

# 精准删除异常行（保留正常数据）
python dm_cli.py clear --date-anomaly --sector 沪深A股 --period 1d
```

**处理上市日期缺失标的（整个文件删除）：**

```bash
# 先 validate 确认上市日期缺失情况
python dm_cli.py validate --sector 沪深A股 --period 1d --detail

# 删除上市日期缺失标的的整个缓存文件
python dm_cli.py clear --no-open-date --sector 沪深A股 --period 1d

# 重新同步数据（删除后必须重新执行 sync）
python dm_cli.py sync --sector 沪深A股 --period 1d
```

### 8.6 注意事项

- **`--sector` 需要板块预先创建**：CLI 通过板块名称从 `~/.qmtquant/cache/pools/` 读取，若板块不存在会报错退出
- **`--symbols` 无需创建板块**：直接传入股票代码，适合临时性操作
- **`--sector` 和 `--symbols` 互斥**：不能同时使用，kline 子类时二选一必填
- **`download` 需要 xqshare 连接**：该命令会触发数据下载，需要 miniQMT/xqshare 在线
- **`schedule` 同样需要 xqshare 连接**：调度服务内部调用 `download`，执行时需要 miniQMT/xqshare 在线；调度服务本身可在无网络时启动，仅在实际执行时才需要连接
- **`sync` 不触发下载**：只读取 miniQMT 已有的本地缓存，无需网络连接
- **多周期用逗号分隔**：`--period 1d,1m,5m`，各周期串行执行
- **`--date-anomaly` 是行级清理**：只删除早于 1990-12-19 的异常行，正常数据保留，文件不删除
- **`--no-open-date` 是文件级删除**：删除整个 Parquet 文件，执行后必须重新执行 `sync` 才能恢复数据
- **`validate` 的 `no_open_date` 检测**：当合约信息中 `open_date` 为 `None` 时，前缺失检测会自动跳过（不误报），该标的不计入健康数量

---

## 九、数据看板（Dashboard）

`dashboard/` 目录提供了一个本地 HTML 数据看板，可直观展示缓存统计、数据健康状况和回测结果，无需启动任何服务，用浏览器直接打开即可。

### 9.1 使用方式

**第一步：导出数据**

```bash
# 在项目根目录执行
python dashboard/dashboard_export.py

# 指定输出路径（可选）
python dashboard/dashboard_export.py --output /path/to/dashboard_data.json
```

导出脚本会依次执行：
1. 收集本地缓存统计信息（`get_statistics()`）
2. **自动扫描所有已有缓存的周期，对每个周期执行完整性检查**（`validate_kline`）
3. 扫描回测结果目录（`backtest_results/`）
4. 将所有数据写入 `dashboard/dashboard_data.json`

**第二步：打开看板**

用浏览器打开 `dashboard/dashboard.html` 即可查看。

---

### 9.2 完整性检查数据（validate_by_period）

`dashboard_export.py` 在导出时会自动对本地 `stock/kline` 缓存中所有已有数据的周期（如 `1d`、`1m`、`5m`）分别执行完整性检查，结果写入 JSON 的 `validate_by_period` 字段。

#### 前置条件

完整性检查依赖以下两个辅助数据文件，**必须提前同步**：

```bash
python dm_cli.py sync --asset stock --sub calendar,instrument
```

若文件缺失，导出时会跳过完整性检查，并在 `validate_by_period` 中写入：

```json
{
  "_skipped": true,
  "reason": "缺少辅助数据文件：trading_calendar.parquet, instrument_detail.parquet"
}
```

#### 数据结构

```json
{
  "validate_by_period": {
    "1d": {
      "summary": {
        "period":       "1d",
        "total":        5000,
        "healthy":      4800,
        "no_cache":     10,
        "field_error":  0,
        "type_error":   0,
        "head_missing": 50,
        "tail_missing": 30,
        "no_open_date": 5,
        "has_gap":      100,
        "checked_at":   "2025-06-16 23:00:00"
      },
      "results": [
        {
          "symbol":       "000001.SZ",
          "has_cache":    true,
          "field_ok":     true,
          "type_ok":      true,
          "head_missing": 0,
          "tail_missing": 0,
          "gap_count":    0,
          "no_open_date": false,
          "cache_start":  "2020-01-02",
          "cache_end":    "2025-06-13"
        }
      ]
    },
    "1m": { "summary": {...}, "results": [...] }
  }
}
```

#### summary 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `period` | str | 数据周期，如 `1d` |
| `total` | int | 本周期总检查股票数 |
| `healthy` | int | 完全健康的股票数（所有维度均通过） |
| `no_cache` | int | 本地无 Parquet 缓存文件的股票数 |
| `field_error` | int | 字段不完整（缺少 required_fields）的股票数 |
| `type_error` | int | 字段类型异常的股票数 |
| `head_missing` | int | 存在前缺失（上市日起数据不完整）的股票数 |
| `tail_missing` | int | 存在后缺失（最新数据未及时更新）的股票数 |
| `no_open_date` | int | 合约信息中 `open_date` 为 `None` 的股票数 |
| `has_gap` | int | 缓存范围内存在中间缺口段的股票数 |
| `checked_at` | str | 检查时间戳，格式 `YYYY-MM-DD HH:MM:SS` |

#### results 每条记录字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | str | 股票代码，如 `000001.SZ` |
| `has_cache` | bool | 是否有本地 Parquet 缓存 |
| `field_ok` | bool | 字段完整度是否通过 |
| `type_ok` | bool | 字段类型是否通过 |
| `head_missing` | int | 前缺失交易日数（0 表示无前缺失） |
| `tail_missing` | int | 后缺失交易日数（0 表示无后缺失） |
| `gap_count` | int | 中间缺口段数（0 表示无缺口） |
| `no_open_date` | bool | 合约信息中 `open_date` 是否缺失 |
| `cache_start` | str\|null | 缓存起始日期，格式 `YYYY-MM-DD` |
| `cache_end` | str\|null | 缓存最新日期，格式 `YYYY-MM-DD` |

---

### 9.3 数据健康 Tab

Dashboard 的"🩺 数据健康"Tab 展示完整性检查结果，位于"数据分析"和"策略绩效"之间。

#### 功能说明

| 功能 | 说明 |
|------|------|
| **周期切换** | 本地有多个周期缓存时，顶部显示周期切换按钮组（如 `1d` / `1m` / `5m`），默认选中第一个周期；只有一个周期时不显示切换按钮 |
| **汇总指标卡片** | 展示 6 项指标：总检查数、健康数（绿色）、无缓存数（灰色）、前缺失数（橙色）、后缺失数（橙色）、中间缺口数（红色） |
| **全健康标识** | 当健康率达到 100% 时，在汇总区域显示绿色"✅ 数据完全健康"横幅 |
| **问题明细表格** | 默认只显示有问题的股票，提供"显示全部"切换按钮 |
| **列排序** | 支持按"前缺失(天)"、"后缺失(天)"、"缺口段数"列头点击排序（升/降序切换） |
| **状态图标** | 每行末尾显示健康状态图标：✅ 健康 / ⚠️ 前后缺失 / 🕳 中间缺口 / ❌ 无缓存或字段异常 |

#### 空状态处理

| 情况 | 展示内容 |
|------|---------|
| `validate_by_period` 字段不存在（旧版 JSON） | 提示"暂无检查数据，请重新运行 `python dashboard_export.py`" |
| `_skipped == true`（辅助数据未就绪） | 提示"辅助数据未就绪"，并显示需要执行的同步命令 |
| 周期列表为空 | 提示"暂无检查数据" |

---

### 9.4 典型工作流

**首次使用看板：**

```bash
# 1. 确保辅助数据已同步
python dm_cli.py sync --asset stock --sub calendar,instrument

# 2. 导出看板数据（含完整性检查）
python dashboard/dashboard_export.py

# 3. 用浏览器打开看板
open dashboard/dashboard.html   # macOS
```

**日常刷新看板：**

```bash
# 重新导出（每次需要查看最新状态时执行）
python dashboard/dashboard_export.py
```

**发现问题后修复：**

```bash
# 看板中发现后缺失较多 → 执行智能下载修复
python dm_cli.py download --sector 沪深A股 --period 1d --mode smart

# 看板中发现中间缺口 → 执行缺口下载修复
python dm_cli.py download --sector 沪深A股 --period 1d --mode gap

# 修复后重新导出看板确认结果
python dashboard/dashboard_export.py
```

> **注意**：`dashboard_export.py` 每次运行都会重新执行完整性检查，对于 5000 只股票的日线数据，检查耗时约 1~3 分钟（取决于机器性能）。终端会每 100 只打印一次进度，并在完成后按周期打印汇总统计。
