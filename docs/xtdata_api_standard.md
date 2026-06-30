# XtQuant.XtData 行情模块 API 文档

> 来源：https://dict.thinktrader.net/nativeApi/xtdata.html?id=dqamF2
> 整理日期：2026-05-16

---

## 概述

`xtdata` 是 xtquant 库中提供行情相关数据的模块，通过与 MiniQmt 建立连接来处理行情数据请求。

**主要数据类型：**
- 行情数据：历史和实时的 K 线、分笔数据
- 财务数据
- 合约基础信息
- 板块和行业分类信息

**接口前缀约定：**

| 前缀 | 含义 |
|------|------|
| `subscribe_` / `unsubscribe_` | 订阅 / 反订阅 |
| `get_` | 获取本地缓存数据 |
| `download_` | 从服务器下载数据到本地 |

**常用参数类型说明：**

| 参数 | 格式 | 示例 |
|------|------|------|
| stock_code | `code.market` | `000001.SZ`、`600000.SH` |
| period（K线） | 字符串 | `tick`、`1m`、`5m`、`15m`、`30m`、`1h`、`1d`、`1w`、`1mon`、`1q`、`1hy`、`1y` |
| dividend_type | 字符串 | `none`、`front`、`back`、`front_ratio`、`back_ratio` |
| 时间字符串 | `YYYYMMDDHHmmss` 或 `YYYYMMDD` | `20240101`、`20240101093000` |

---

## 一、行情订阅接口

---

### subscribe_quote — 订阅单股行情

**函数签名**
```python
subscribe_quote(stock_code, period='1d', start_time='', end_time='', count=0, callback=None)
```

**说明**

订阅单股的行情数据。数据推送通过 `callback` 回调返回，数据类型与 `period` 指定的周期对应。历史数据范围参数用于保证数据连续性，仅订阅实时数据时传 `count=0` 即可。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_code | string | ✅ | — | 合约代码，格式 `code.market` |
| period | string | ❌ | `'1d'` | 数据周期 |
| start_time | string | ❌ | `''` | 历史数据起始时间，为空表示最早 |
| end_time | string | ❌ | `''` | 历史数据结束时间，为空表示最新 |
| count | int | ❌ | `0` | 历史数据条数，`0` 表示不请求历史数据 |
| callback | callable | ❌ | `None` | 数据推送回调函数，签名为 `on_data(datas)` |

**回调参数格式**
```python
# datas 格式：{ stock_code: [data1, data2, ...] }
def on_data(datas):
    for stock_code in datas:
        print(stock_code, datas[stock_code])
```

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 订阅号，成功返回 `> 0`，失败返回 `-1` |

**备注**
- 单股订阅数量建议不超过 50，订阅数较多时推荐使用 `subscribe_whole_quote`

---

### subscribe_whole_quote — 订阅全推行情

**函数签名**
```python
subscribe_whole_quote(code_list, callback=None)
```

**说明**

订阅全推行情数据，数据类型为分笔数据。订阅后会首先返回当前最新的全推快照数据。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| code_list | list | ✅ | — | 市场代码列表（如 `['SH','SZ']`）或合约代码列表（如 `['600000.SH']`） |
| callback | callable | ❌ | `None` | 数据推送回调，签名为 `on_data(datas)` |

**回调参数格式**
```python
# datas 格式：{ stock1: data1, stock2: data2, ... }
def on_data(datas):
    for stock_code in datas:
        print(stock_code, datas[stock_code])
```

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 订阅号，成功返回 `> 0`，失败返回 `-1` |

**备注**
- 全推数据是高订阅数场景的推荐方案，流量和处理效率均优于单股订阅

---

### unsubscribe_quote — 反订阅行情数据

**函数签名**
```python
unsubscribe_quote(seq)
```

**说明**

取消已订阅的行情数据。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| seq | int | ✅ | 订阅时返回的订阅号 |

**返回格式**

无返回值。

---

### run — 阻塞线程接收行情回调

**函数签名**
```python
run()
```

**说明**

阻塞当前线程以维持运行状态，一般用于订阅数据后持续处理回调。

**输入参数**

无。

**返回格式**

无返回值。

**备注**
- 实现方式为持续循环 sleep，唤醒时检查连接状态，若连接断开则抛出异常结束循环

---

## 二、行情数据获取接口

---

### get_market_data — 获取行情数据（缓存）

**函数签名**
```python
get_market_data(field_list=[], stock_list=[], period='1d', start_time='', end_time='', count=-1, dividend_type='none', fill_data=True)
```

**说明**

从本地缓存获取行情数据，是主动获取行情的主要接口。使用前需确保已通过 `download_history_data` 下载了所需数据。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| field_list | list | ❌ | `[]` | 数据字段列表，传空则返回全部字段 |
| stock_list | list | ❌ | `[]` | 合约代码列表 |
| period | string | ❌ | `'1d'` | 数据周期 |
| start_time | string | ❌ | `''` | 起始时间，为空表示最早 |
| end_time | string | ❌ | `''` | 结束时间，为空表示最新 |
| count | int | ❌ | `-1` | 数据条数；`-1` 返回全部；`≥0` 时以 end_time 为基准向前取 count 条 |
| dividend_type | string | ❌ | `'none'` | 复权方式，对 tick 数据无效 |
| fill_data | bool | ❌ | `True` | 是否向后填充空缺数据 |

**返回格式**

- **K 线周期**（`1m`、`5m`、`1d` 等）：
  ```
  dict { field: pd.DataFrame }
  # DataFrame: index=stock_list, columns=time_list
  ```

- **分笔周期**（`tick`）：
  ```
  dict { stock_code: np.ndarray }
  # ndarray 按时间戳 time 升序排列
  ```

**备注**
- 获取 Level2 数据需要数据终端有 L2 数据权限
- 时间范围为闭区间 `[start_time, end_time]`

---

### get_local_data — 获取本地行情数据（文件直读）

**函数签名**
```python
get_local_data(field_list=[], stock_list=[], period='1d', start_time='', end_time='', count=-1, dividend_type='none', fill_data=True, data_dir=data_dir)
```

**说明**

直接从本地数据文件读取行情数据，适合快速批量获取历史数据，绕过 MiniQmt 连接层。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| field_list | list | ❌ | `[]` | 数据字段列表，传空则返回全部字段 |
| stock_list | list | ❌ | `[]` | 合约代码列表 |
| period | string | ❌ | `'1d'` | 数据周期 |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| count | int | ❌ | `-1` | 数据条数，`-1` 返回全部 |
| dividend_type | string | ❌ | `'none'` | 复权方式 |
| fill_data | bool | ❌ | `True` | 是否向后填充空缺数据 |
| data_dir | string | ❌ | 自动获取 | MiniQmt 的 userdata_mini 路径，默认自动获取，也可手动指定或修改 `xtdata.data_dir` |

**返回格式**

与 `get_market_data` 相同。

**备注**
- 仅支持 Level1 数据

---

### get_full_tick — 获取全推数据

**函数签名**
```python
get_full_tick(code_list)
```

**说明**

获取当前最新的全推分笔快照数据。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code_list | list | ✅ | 市场代码（如 `['SH','SZ']`）或合约代码列表（如 `['600000.SH']`） |

**返回格式**

```
dict { stock_code: data }
```

---

### get_full_kline — 获取最新交易日 K 线全推数据

**函数签名**
```python
get_full_kline(field_list=[], stock_list=[], period='1m', start_time='', end_time='', count=1, dividend_type='none', fill_data=True)
```

**说明**

获取最新交易日的 K 线全推数据，仅支持最新一个交易日，不包含历史数据。

**输入参数**

参数含义与 `get_market_data` 相同，参见该接口说明。

**返回格式**

```
dict { field: pd.DataFrame }
```

**备注**
- 仅返回最新交易日数据，不含历史

---

### get_divid_factors — 获取除权数据

**函数签名**
```python
get_divid_factors(stock_code, start_time='', end_time='')
```

**说明**

获取指定合约的除权除息数据，用于手动计算复权价格。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_code | string | ✅ | — | 合约代码 |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |

**返回格式**

```
pd.DataFrame
# 字段：interest, stockBonus, stockGift, allotNum, allotPrice, gugai, dr
```

---

## 三、行情数据下载接口

---

### download_history_data — 下载历史行情数据（单合约）

**函数签名**
```python
download_history_data(stock_code, period, start_time='', end_time='', incrementally=None)
```

**说明**

从服务器下载单个合约的历史行情数据到本地，同步执行，完成后返回。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_code | string | ✅ | — | 合约代码 |
| period | string | ✅ | — | 数据周期 |
| start_time | string | ❌ | `''` | 起始时间，为空时触发增量下载 |
| end_time | string | ❌ | `''` | 结束时间 |
| incrementally | bool/None | ❌ | `None` | `True`：增量下载；`False`：全量下载；`None`：由 start_time 是否为空决定 |

**返回格式**

无返回值。

**备注**
- 同步执行，阻塞直到下载完成
- 增量下载时从本地最后一条数据往后下载

---

### download_history_data2 — 下载历史行情数据（批量）

**函数签名**
```python
download_history_data2(stock_list, period, start_time='', end_time='', callback=None, incrementally=None)
```

**说明**

批量下载多个合约的历史行情数据，支持进度回调。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_list | list | ✅ | — | 合约代码列表 |
| period | string | ✅ | — | 数据周期 |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| callback | callable | ❌ | `None` | 进度回调，参数为进度 dict |
| incrementally | bool/None | ❌ | `None` | 是否增量下载，同 `download_history_data` |

**回调参数格式**
```python
# data 格式：
# { 'finished': 1, 'total': 50, 'stockcode': '000001.SZ', 'message': '' }
def on_progress(data):
    print(data)
```

**返回格式**

无返回值。

**备注**
- 同步执行，每完成一个合约触发一次回调

---

### download_history_contracts — 下载过期（退市）合约信息

**函数签名**
```python
download_history_contracts()
```

**说明**

下载过期或退市合约的基础信息，下载后可通过 `get_stock_list_in_sector` 获取过期标的列表。

**输入参数**

无。

**返回格式**

无返回值。

**备注**
- 同步执行
- 过期板块名称查看：`print([i for i in xtdata.get_sector_list() if "过期" in i])`
- 下载后可通过 `xtdata.get_instrument_detail()` 查看过期合约信息

---

## 四、财务数据接口

---

### get_financial_data — 获取财务数据

**函数签名**
```python
get_financial_data(stock_list, table_list=[], start_time='', end_time='', report_type='report_time')
```

**说明**

从本地缓存获取财务报表数据，使用前需先调用 `download_financial_data` 下载。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_list | list | ✅ | — | 合约代码列表 |
| table_list | list | ❌ | `[]` | 财务表名列表，传空则返回全部表 |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| report_type | string | ❌ | `'report_time'` | 筛选方式：`'report_time'`（截止日期）或 `'announce_time'`（披露日期） |

**可选财务表名**

| 表名 | 说明 |
|------|------|
| `Balance` | 资产负债表 |
| `Income` | 利润表 |
| `CashFlow` | 现金流量表 |
| `Capital` | 股本表 |
| `Holdernum` | 股东数 |
| `Top10holder` | 十大股东 |
| `Top10flowholder` | 十大流通股东 |
| `Pershareindex` | 每股指标 |

**返回格式**

```
dict {
    stock_code: {
        table_name: pd.DataFrame
    }
}
```

---

### download_financial_data — 下载财务数据（基础版）

**函数签名**
```python
download_financial_data(stock_list, table_list=[])
```

**说明**

下载指定合约的财务数据到本地，同步执行。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_list | list | ✅ | — | 合约代码列表 |
| table_list | list | ❌ | `[]` | 财务表名列表，传空则下载全部 |

**返回格式**

无返回值。

---

### download_financial_data2 — 下载财务数据（增强版）

**函数签名**
```python
download_financial_data2(stock_list, table_list=[], start_time='', end_time='', callback=None)
```

**说明**

下载财务数据的增强版本，支持按披露日期范围筛选和进度回调。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_list | list | ✅ | — | 合约代码列表 |
| table_list | list | ❌ | `[]` | 财务表名列表 |
| start_time | string | ❌ | `''` | 起始时间（按 `m_anntime` 披露日期筛选） |
| end_time | string | ❌ | `''` | 结束时间（按 `m_anntime` 披露日期筛选） |
| callback | callable | ❌ | `None` | 进度回调，参数格式同 `download_history_data2` |

**返回格式**

无返回值。

**备注**
- 同步执行，按披露日期 `[start_time, end_time]` 范围筛选下载

---

## 五、合约基础信息接口

---

### get_instrument_detail — 获取合约基础信息

**函数签名**
```python
get_instrument_detail(stock_code, iscomplete=False)
```

**说明**

获取单个合约的基础信息字典，可用于验证合约代码是否有效。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| stock_code | string | ✅ | — | 合约代码 |
| iscomplete | bool | ❌ | `False` | `False`：返回常用字段；`True`：返回全部字段 |

**返回格式**

找不到合约时返回 `None`，否则返回：

```
dict { field: value }
```

**常用字段（iscomplete=False）**

| 字段 | 类型 | 说明 |
|------|------|------|
| ExchangeID | string | 合约市场代码 |
| InstrumentID | string | 合约代码 |
| InstrumentName | string | 合约名称 |
| ProductID | string | 品种ID（期货） |
| ExchangeCode | string | 交易所代码 |
| UniCode | string | 统一规则代码 |
| CreateDate | str | 上市日期（期货） |
| OpenDate | str | IPO 日期（股票） |
| ExpireDate | int | 退市日或到期日 |
| PreClose | float | 前收盘价 |
| SettlementPrice | float | 前结算价 |
| UpStopPrice | float | 当日涨停价 |
| DownStopPrice | float | 当日跌停价 |
| FloatVolume | float | 流通股本 |
| TotalVolume | float | 总股本 |
| PriceTick | float | 最小价格变动单位 |
| VolumeMultiple | int | 合约乘数（非期货默认为 1） |
| MainContract | int | 主力合约标记（1/2/3 分别为第一/二/三主力） |
| IsTrading | bool | 是否可交易 |

**备注**
- `iscomplete=True` 时额外返回手续费率、期权类型等字段，详见附录合约信息字段列表

---

### get_instrument_type — 获取合约类型

**函数签名**
```python
get_instrument_type(stock_code)
```

**说明**

获取合约所属类型标记。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| stock_code | string | ✅ | 合约代码 |

**返回格式**

找不到合约时返回 `None`，否则返回：

```
dict { type_name: bool }
# 例如：{'index': False, 'stock': True, 'fund': False, 'etf': False}
```

| 键名 | 说明 |
|------|------|
| `index` | 是否为指数 |
| `stock` | 是否为股票 |
| `fund` | 是否为基金 |
| `etf` | 是否为 ETF |

---

## 六、交易日历接口

---

### get_trading_dates — 获取交易日列表

**函数签名**
```python
get_trading_dates(market, start_time='', end_time='', count=-1)
```

**说明**

获取指定市场在时间范围内的交易日列表。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| market | string | ✅ | — | 市场代码，如 `'SH'`、`'SZ'` |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| count | int | ❌ | `-1` | 返回条数，`-1` 返回全部 |

**返回格式**

```
list [date1, date2, ...]  # 时间戳列表
```

---

### get_trading_calendar — 获取交易日历

**函数签名**
```python
get_trading_calendar(market, start_time='', end_time='')
```

**说明**

获取指定市场的完整交易日历，支持查询未来交易日。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| market | string | ✅ | — | 市场代码 |
| start_time | string | ❌ | `''` | 起始时间（8位字符串），为空表示该市场首个交易日 |
| end_time | string | ❌ | `''` | 结束时间（8位字符串），为空表示当前时间，可填未来时间 |

**返回格式**

```
list  # 完整交易日列表
```

**备注**
- 需要先调用 `download_holiday_data` 下载节假日数据

---

### get_holidays — 获取节假日数据

**函数签名**
```python
get_holidays()
```

**说明**

获取截止到当年的节假日日期列表。

**输入参数**

无。

**返回格式**

```
list ['20240101', '20240215', ...]  # 8位日期字符串
```

---

### download_holiday_data — 下载节假日数据

**函数签名**
```python
download_holiday_data()
```

**说明**

从服务器下载节假日数据到本地。

**输入参数**

无。

**返回格式**

无返回值。

---

## 七、板块管理接口

---

### get_sector_list — 获取板块列表

**函数签名**
```python
get_sector_list()
```

**说明**

获取所有可用板块的名称列表。

**输入参数**

无。

**返回格式**

```
list ['板块1', '板块2', ...]
```

**备注**
- 需要先调用 `download_sector_data` 下载板块分类信息

---

### get_stock_list_in_sector — 获取板块成分股列表

**函数签名**
```python
get_stock_list_in_sector(sector_name, real_timetag=None)
```

**说明**

获取指定板块的成分股代码列表。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| sector_name | string | ✅ | — | 板块名称 |
| real_timetag | 可选 | ❌ | `None` | 指定时间点的成分股（2024-05-27 新增） |

**返回格式**

```
list ['000001.SZ', '600000.SH', ...]
```

---

### download_sector_data — 下载板块分类信息

**函数签名**
```python
download_sector_data()
```

**说明**

从服务器下载板块分类信息到本地，同步执行。

**输入参数**

无。

**返回格式**

无返回值。

**备注**
- 板块分类信息更新频率低，按周或按日定期下载即可

---

### create_sector_folder — 创建板块目录节点

**函数签名**
```python
create_sector_folder(parent_node, folder_name, overwrite=True)
```

**说明**

在板块树中创建一个目录节点（文件夹）。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| parent_node | string | ✅ | — | 父节点名称，`' '` 表示"我的"默认目录 |
| folder_name | string | ✅ | — | 要创建的目录名称 |
| overwrite | bool | ❌ | `True` | `True`：已存在则跳过；`False`：自动追加数字编号 |

**返回格式**

```
string  # 实际创建的目录名
```

---

### create_sector — 创建板块

**函数签名**
```python
create_sector(parent_node, sector_name, overwrite=True)
```

**说明**

在指定目录下创建一个板块。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| parent_node | string | ✅ | — | 父节点名称 |
| sector_name | string | ✅ | — | 板块名称 |
| overwrite | bool | ❌ | `True` | 是否覆盖已有同名板块 |

**返回格式**

```
string  # 实际创建的板块名
```

---

### add_sector — 添加自定义板块成分股

**函数签名**
```python
add_sector(sector_name, stock_list)
```

**说明**

向指定板块中添加成分股。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| sector_name | string | ✅ | 板块名称 |
| stock_list | list | ✅ | 要添加的成分股代码列表 |

**返回格式**

无返回值。

---

### remove_stock_from_sector — 移除板块成分股

**函数签名**
```python
remove_stock_from_sector(sector_name, stock_list)
```

**说明**

从指定板块中移除成分股。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| sector_name | string | ✅ | 板块名称 |
| stock_list | list | ✅ | 要移除的成分股代码列表 |

**返回格式**

```
bool  # True 成功，False 失败
```

---

### remove_sector — 移除自定义板块

**函数签名**
```python
remove_sector(sector_name)
```

**说明**

删除指定的自定义板块。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| sector_name | string | ✅ | 板块名称 |

**返回格式**

无返回值。

---

### reset_sector — 重置板块成分股

**函数签名**
```python
reset_sector(sector_name, stock_list)
```

**说明**

用新的成分股列表替换板块中的全部成分股。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| sector_name | string | ✅ | 板块名称 |
| stock_list | list | ✅ | 新的成分股代码列表 |

**返回格式**

```
bool  # True 成功，False 失败
```

---

## 八、指数成分权重接口

---

### get_index_weight — 获取指数成分权重

**函数签名**
```python
get_index_weight(index_code)
```

**说明**

获取指数各成分股的权重信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| index_code | string | ✅ | 指数代码，如 `'000300.SH'` |

**返回格式**

```
dict { stock_code: weight }
# 例如：{'600000.SH': 0.012, '000001.SZ': 0.008, ...}
```

**备注**
- 需要先调用 `download_index_weight` 下载数据

---

### download_index_weight — 下载指数成分权重信息

**函数签名**
```python
download_index_weight()
```

**说明**

从服务器下载指数成分权重信息到本地，同步执行。

**输入参数**

无。

**返回格式**

无返回值。

---

## 九、可转债接口

---

### download_cb_data — 下载可转债基础信息

**函数签名**
```python
download_cb_data()
```

**说明**

下载全部可转债基础信息到本地。

**输入参数**

无。

**返回格式**

无返回值。

---

### get_cb_info — 获取可转债基础信息

**函数签名**
```python
get_cb_info(stockcode)
```

**说明**

获取指定可转债的基础信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| stockcode | string | ✅ | 可转债代码 |

**返回格式**

可转债基础信息字典。

**备注**
- 需要先调用 `download_cb_data` 下载数据

---

## 十、ETF 申赎清单接口

---

### download_etf_info — 下载 ETF 申赎清单信息

**函数签名**
```python
download_etf_info()
```

**说明**

下载所有 ETF 申赎清单信息到本地。

**输入参数**

无。

**返回格式**

无返回值。

---

### get_etf_info — 获取 ETF 申赎清单信息

**函数签名**
```python
get_etf_info()
```

**说明**

获取所有 ETF 申赎清单信息。

**输入参数**

无。

**返回格式**

```
dict  # 所有 ETF 申赎数据
```

---

## 十一、新股申购接口

---

### get_ipo_info — 获取新股申购信息

**函数签名**
```python
get_ipo_info(start_time, end_time)
```

**说明**

返回指定时间范围内的新股申购信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| start_time | string | ❌ | 开始日期，如 `'20230327'`，为空返回全部 |
| end_time | string | ❌ | 结束日期，如 `'20230327'`，为空返回全部 |

**返回格式**

```
list[dict]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| securityCode | string | 证券代码 |
| codeName | string | 代码简称 |
| market | string | 所属市场 |
| actIssueQty | int | 发行总量（股） |
| onlineIssueQty | int | 网上发行量（股） |
| onlineSubCode | string | 申购代码 |
| onlineSubMaxQty | int | 申购上限（股） |
| publishPrice | float | 发行价格 |
| isProfit | int | 是否已盈利（0：未盈利，1：已盈利） |
| industryPe | float | 行业市盈率 |
| afterPE | float | 发行后市盈率 |

---

## 十二、周期与可用性接口

---

### get_period_list — 获取可用周期列表

**函数签名**
```python
get_period_list()
```

**说明**

返回当前连接环境下可用的数据周期列表。

**输入参数**

无。

**返回格式**

```
list  # 周期字符串列表，如 ['tick', '1m', '5m', '1d', ...]
```

---

## 十三、模型调用接口（投研版）

---

### subscribe_formula — 订阅 VBA 模型

**函数签名**
```python
subscribe_formula(formula_name, stock_code, period, start_time='', end_time='', count=-1, dividend_type=None, extend_param={}, callback=None)
```

**说明**

订阅 VBA 模型的运行结果，需连接投研端使用。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| formula_name | string | ✅ | — | 模型名称 |
| stock_code | string | ✅ | — | 主图合约代码 |
| period | string | ✅ | — | K 线周期 |
| start_time | string | ❌ | `''` | 起始时间，为空表示最早 |
| end_time | string | ❌ | `''` | 结束时间，为空表示最新 |
| count | int | ❌ | `-1` | 向前运行的 bar 数，`-1` 运行全部 |
| dividend_type | string | ❌ | `None` | 复权方式，默认使用主图除权方式 |
| extend_param | dict | ❌ | `{}` | 模型入参，格式 `{'参数名': 值}`；可含 `__basket` 指定组合权重 |
| callback | callable | ❌ | `None` | 结果推送回调 |

**返回格式**

```
int  # 订阅成功返回订阅ID（>0），失败返回 -1
```

**备注**
- 需要先补充本地 K 线或分笔数据
- 需连接投研端使用

---

### unsubscribe_formula — 反订阅模型

**函数签名**
```python
unsubscribe_formula(subID)
```

**说明**

取消已订阅的 VBA 模型。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| subID | int | ✅ | 订阅时返回的订阅 ID |

**返回格式**

```
bool  # True 成功，False 失败
```

---

### call_formula — 调用 VBA 模型（单合约）

**函数签名**
```python
call_formula(formula_name, stock_code, period, start_time='', end_time='', count=-1, dividend_type='none', extend_param={})
```

**说明**

同步获取 VBA 模型的运行结果，需连接投研端使用。

**输入参数**

参数含义与 `subscribe_formula` 相同，无 `callback` 参数。

**返回格式**

```python
dict {
    'dbt': 0,           # 返回数据类型，0 表示全部历史数据
    'timelist': [...],  # 时间范围列表
    'outputs': {
        'var1': [...],  # 输出变量名: 变量值列表
        'var2': [...]
    }
}
```

**备注**
- 需要先补充本地 K 线或分笔数据

---

### call_formula_batch — 批量调用 VBA 模型

**函数签名**
```python
call_formula_batch(formula_names, stock_codes, period, start_time='', end_time='', count=-1, dividend_type='none', extend_params=[])
```

**说明**

批量同步获取多个模型、多个合约的运行结果。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| formula_names | list | ✅ | — | 模型名称列表 |
| stock_codes | list | ✅ | — | 合约代码列表 |
| period | string | ✅ | — | K 线周期 |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| count | int | ❌ | `-1` | 向前运行的 bar 数 |
| dividend_type | string | ❌ | `'none'` | 复权方式 |
| extend_params | list | ❌ | `[]` | 每个模型的入参列表，格式 `[{'模型名:参数名': 值}]` |

**返回格式**

```python
list[dict]
# 每个 dict 包含：
# { 'formula': 模型名, 'stock': 合约代码, 'argument': 参数, 'result': call_formula 返回格式 }
```

---

### generate_index_data — 生成因子数据文件

**函数签名**
```python
generate_index_data(formula_name, formula_param={}, stock_list=[], period='1d', dividend_type='none', start_time='', end_time='', fill_mode='fixed', fill_value=float('nan'), result_path=None)
```

**说明**

在本地生成 feather 格式的因子数据文件，需连接投研端使用。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| formula_name | string | ✅ | — | 模型名称（需存在于投研端） |
| formula_param | dict | ❌ | `{}` | 模型参数，如 `{'param1': 1.0}` |
| stock_list | list | ❌ | `[]` | 股票列表 |
| period | string | ❌ | `'1d'` | 周期，可选 `'1m'`、`'5m'`、`'1d'` |
| dividend_type | string | ❌ | `'none'` | 复权方式，可选 `'none'`、`'front_ratio'`、`'back_ratio'` |
| start_time | string | ❌ | `''` | 起始时间 |
| end_time | string | ❌ | `''` | 结束时间 |
| fill_mode | string | ❌ | `'fixed'` | 空缺填充方式：`'fixed'`（固定值）或 `'forward'`（向前延续） |
| fill_value | float | ❌ | `float('nan')` | 固定填充值 |
| result_path | string | ❌ | `None` | 输出文件路径（feather 格式） |

**返回格式**

`None`

**备注**
- 必须连接投研端使用

---

## 附录 A：行情数据字段说明

### tick — 分笔数据字段

| 字段 | 说明 |
|------|------|
| time | 时间戳 |
| lastPrice | 最新价 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| lastClose | 前收盘价 |
| amount | 成交总额 |
| volume | 成交总量 |
| pvolume | 原始成交总量 |
| stockStatus | 证券状态 |
| openInt | 持仓量 |
| lastSettlementPrice | 前结算 |
| askPrice | 委卖价（多档） |
| bidPrice | 委买价（多档） |
| askVol | 委卖量 |
| bidVol | 委买量 |
| transactionNum | 成交笔数 |

### 1m / 5m / 1d — K 线数据字段

| 字段 | 说明 |
|------|------|
| time | 时间戳 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| amount | 成交额 |
| settelementPrice | 今结算 |
| openInterest | 持仓量 |
| preClose | 前收价 |
| suspendFlag | 停牌标记（0：正常，1：停牌，-1：当日起复牌） |

### Level2 数据字段

**l2quote — Level2 实时行情快照**

在 tick 字段基础上增加：`transactionNum`（成交笔数）、`settlementPrice`（今结算）、`pe`（市盈率）、多档 `askPrice`/`bidPrice`/`askVol`/`bidVol`

**l2order — Level2 逐笔委托**

| 字段 | 说明 |
|------|------|
| time | 时间戳 |
| price | 委托价 |
| volume | 委托量 |
| entrustNo | 委托号 |
| entrustType | 委托类型 |
| entrustDirection | 委托方向 |

**l2transaction — Level2 逐笔成交**

| 字段 | 说明 |
|------|------|
| time | 时间戳 |
| price | 成交价 |
| volume | 成交量 |
| amount | 成交额 |
| tradeIndex | 成交记录号 |
| buyNo | 买方委托号 |
| sellNo | 卖方委托号 |
| tradeType | 成交类型 |
| tradeFlag | 成交标志 |

**l2quoteaux — Level2 实时行情补充（总买总卖）**

| 字段 | 说明 |
|------|------|
| avgBidPrice | 委买均价 |
| totalBidQuantity | 委买总量 |
| avgOffPrice | 委卖均价 |
| totalOffQuantity | 委卖总量 |
| withdrawBidQuantity | 买入撤单总量 |
| withdrawOffQuantity | 卖出撤单总量 |

---

## 附录 B：枚举值说明

### 证券状态（stockStatus）

| 值 | 说明 |
|----|------|
| 0, 10 | 未知 |
| 11 | 开盘前 S |
| 12 | 集合竞价 C |
| 13 | 连续交易 T |
| 14 | 休市 B |
| 15 | 闭市 E |
| 16 | 波动性中断 V |
| 17 | 临时停牌 P |
| 18 | 收盘集合竞价 U |
| 19 | 盘中集合竞价 M |
| 20 | 暂停交易至闭市 N |
| 22 | 盘后固定价格行情 |
| 23 | 盘后固定价格行情完毕 |

### 委托类型（entrustType / tradeType）

| 值 | 说明 |
|----|------|
| 0 | 未知 |
| 1 | 正常交易业务 |
| 2 | 即时成交剩余撤销 |
| 3 | ETF 基金申报 |
| 4 | 最优五档即时成交剩余撤销 |
| 5 | 全额成交或撤销 |
| 6 | 本方最优价格 |
| 7 | 对手方最优价格 |

### 委托方向（entrustDirection）

| 值 | 说明 |
|----|------|
| 1 | 买入 |
| 2 | 卖出 |
| 3 | 撤买（上交所） |
| 4 | 撤卖（上交所） |

### 成交标志（tradeFlag）

| 值 | 说明 |
|----|------|
| 0 | 未知 |
| 1 | 外盘 |
| 2 | 内盘 |
| 3 | 撤单（深交所） |

### 现金替代标志（ETF 申赎清单）

| 值 | 说明 |
|----|------|
| 0 | 禁止现金替代（必须有股票） |
| 1 | 允许现金替代（股票不足时用现金） |
| 2 | 必须现金替代 |
| 3 | 非沪市退补现金替代 |
| 4 | 非沪市必须现金替代 |
| 5 | 非沪深退补现金替代 |
| 6 | 非沪深必须现金替代 |
| 7 | 港市退补现金替代（跨沪深 ETF） |
| 8 | 港市必须现金替代（跨沪深港 ETF） |

---

## 附录 C：工具函数

### 时间戳转换示例

```python
import time

def conv_time(ct):
    """
    将毫秒时间戳转换为时间字符串
    conv_time(1476374400000) --> '20161014000000.000'
    """
    local_time = time.localtime(ct / 1000)
    data_head = time.strftime('%Y%m%d%H%M%S', local_time)
    data_secs = (ct - int(ct)) * 1000
    time_stamp = '%s.%03d' % (data_head, data_secs)
    return time_stamp
```
