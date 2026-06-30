# XtQuant.XtTrader 交易模块 API 文档

> 来源：https://dict.thinktrader.net/nativeApi/xttrader.html?id=dqamF2
> 整理日期：2026-05-16

---

## 概述

`XtQuantTrader` 是 xtquant 库中提供交易功能的核心模块，通过与 MiniQMT 客户端建立连接，实现报单、撤单、查询资产/委托/成交/持仓，以及接收资金、委托、成交和持仓等变动的主推消息。

**模块导入：**
```python
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
```

**账号对象创建：**
```python
# 普通股票账号
acc = StockAccount('1000000365')
# 指定账号类型
acc = StockAccount('1000000365', 'STOCK')      # 股票
acc = StockAccount('1208970161', 'CREDIT')     # 信用
acc = StockAccount('1000000365', 'FUTURE')     # 期货
acc = StockAccount('1000000365', 'HUGANGTONG') # 沪港通
acc = StockAccount('1000000365', 'SHENGANGTONG') # 深港通
```

---

## 一、系统设置接口

---

### XtQuantTrader — 创建 API 实例

**函数签名**
```python
XtQuantTrader(path, session_id)
```

**说明**

创建 XtQuant API 的实例对象，后续所有操作均基于该实例。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | str | ✅ | MiniQMT 客户端 `userdata_mini` 的完整路径 |
| session_id | int | ✅ | 与 MiniQMT 通信的会话 ID，不同 Python 策略需使用不同会话编号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| XtQuantTrader | API 实例对象 |

**备注**
- 通常情况下只需创建一个 API 实例
- 不同策略进程必须使用不同的 `session_id`，否则会话冲突

**示例**
```python
path = 'D:\\迅投极速交易终端 睿智融科版\\userdata_mini'
session_id = 123456
xt_trader = XtQuantTrader(path, session_id)
```

---

### register_callback — 注册回调类

**函数签名**
```python
xt_trader.register_callback(callback)
```

**说明**

将回调类实例注册到 API 实例中，用于接收交易主推消息（委托、成交、撤单失败等）。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| callback | XtQuantTraderCallback | ✅ | 回调类实例对象 |

**返回格式**

无。

**备注**
- 需在 `start()` 之前调用

**示例**
```python
class MyCallback(XtQuantTraderCallback):
    pass

callback = MyCallback()
xt_trader.register_callback(callback)
```

---

### start — 准备 API 环境

**函数签名**
```python
xt_trader.start()
```

**说明**

启动交易线程，准备交易所需的运行环境。

**输入参数**

无。

**返回格式**

无。

**备注**
- 必须在 `connect()` 之前调用

**示例**
```python
xt_trader.start()
```

---

### connect — 创建连接

**函数签名**
```python
xt_trader.connect()
```

**说明**

连接 MiniQMT 客户端，建立通信通道。

**输入参数**

无。

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 连接成功返回 `0`，失败返回非 `0` |

**备注**
- 该连接为一次性连接，断开后不会自动重连，需再次主动调用

**示例**
```python
connect_result = xt_trader.connect()
print(connect_result)  # 0 表示连接成功
```

---

### stop — 停止运行

**函数签名**
```python
xt_trader.stop()
```

**说明**

停止 API 接口，释放资源。

**输入参数**

无。

**返回格式**

无。

**示例**
```python
xt_trader.stop()
```

---

### run_forever — 阻塞线程等待

**函数签名**
```python
xt_trader.run_forever()
```

**说明**

阻塞当前线程，进入等待状态，持续接收交易主推消息，直到 `stop()` 被调用。

**输入参数**

无。

**返回格式**

无。

**备注**
- 支持 `Ctrl+C` 中断退出

**示例**
```python
xt_trader.run_forever()
```

---

### set_relaxed_response_order_enabled — 开启主动请求专用线程

**函数签名**
```python
xt_trader.set_relaxed_response_order_enabled(enabled)
```

**说明**

控制主动请求接口的返回是否从额外的专用线程返回，以获得宽松的数据时序。开启后，可在 `on_stock_order` 等推送回调中调用同步查询接口而不会卡住。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| enabled | bool | ✅ | `False` | `True`：开启专用线程；`False`：关闭（默认） |

**返回格式**

无。

**备注**
- 开启后查询和推送的数据在时序上会变得不确定（查询结果可能比早于它的推送数据更新）
- 通常推荐在推送回调中使用异步查询接口（如 `query_stock_orders_async`），而非开启此选项

---

## 二、操作接口

---

### subscribe — 订阅账号信息

**函数签名**
```python
xt_trader.subscribe(account)
```

**说明**

订阅指定资金账号的信息，订阅后可收到该账号的委托、成交、持仓等变动主推。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号对象 |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 订阅成功返回 `0`，失败返回 `-1` |

**示例**
```python
account = StockAccount('1000000365')
subscribe_result = xt_trader.subscribe(account)
```

---

### unsubscribe — 反订阅账号信息

**函数签名**
```python
xt_trader.unsubscribe(account)
```

**说明**

取消订阅指定资金账号的信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号对象 |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回 `0`，失败返回 `-1` |

**示例**
```python
account = StockAccount('1000000365')
unsubscribe_result = xt_trader.unsubscribe(account)
```

---

### order_stock — 股票同步报单

**函数签名**
```python
xt_trader.order_stock(account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark)
```

**说明**

对股票进行同步下单操作，阻塞直到收到委托结果。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| stock_code | str | ✅ | 证券代码，如 `'600000.SH'` |
| order_type | int | ✅ | 委托类型，见数据字典 `order_type` |
| order_volume | int | ✅ | 委托数量，股票单位为"股"，债券单位为"张" |
| price_type | int | ✅ | 报价类型，见数据字典 `price_type` |
| price | float | ✅ | 委托价格 |
| strategy_name | str | ✅ | 策略名称 |
| order_remark | str | ✅ | 委托备注 |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回大于 `0` 的订单编号；失败返回 `-1` |

**备注**
- 返回的订单编号可用于后续撤单操作

**示例**
```python
account = StockAccount('1000000365')
order_id = xt_trader.order_stock(
    account, '600000.SH', xtconstant.STOCK_BUY,
    1000, xtconstant.FIX_PRICE, 10.5,
    'strategy1', 'order_test'
)
```

---

### order_stock_async — 股票异步报单

**函数签名**
```python
xt_trader.order_stock_async(account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark)
```

**说明**

对股票进行异步下单操作，立即返回请求序号，委托结果通过 `on_order_stock_async_response` 回调推送。

**输入参数**

参数含义与 `order_stock` 完全相同。

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回大于 `0` 的请求序号 `seq`；失败返回 `-1` |

**备注**
- 下单失败时通过 `on_order_error` 推送失败信息
- `seq` 可与 `on_order_stock_async_response` 的 `response.seq` 对应

**示例**
```python
account = StockAccount('1000000365')
seq = xt_trader.order_stock_async(
    account, '600000.SH', xtconstant.STOCK_BUY,
    1000, xtconstant.FIX_PRICE, 10.5,
    'strategy1', 'order_test'
)
```

---

### cancel_order_stock — 股票同步撤单（按订单编号）

**函数签名**
```python
xt_trader.cancel_order_stock(account, order_id)
```

**说明**

根据本地订单编号对委托进行同步撤单操作。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| order_id | int | ✅ | `order_stock` 返回的订单编号；期货使用 `order.order_sysid` |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功发出撤单指令返回 `0`；失败返回 `-1` |

**示例**
```python
account = StockAccount('1000000365')
cancel_result = xt_trader.cancel_order_stock(account, order_id)
```

---

### cancel_order_stock_sysid — 股票同步撤单（按柜台合同编号）

**函数签名**
```python
xt_trader.cancel_order_stock_sysid(account, market, order_sysid)
```

**说明**

根据券商柜台返回的合同编号对委托进行同步撤单操作。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| market | int | ✅ | 交易市场，见数据字典 `market` |
| order_sysid | str | ✅ | 券商柜台的合同编号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回 `0`；失败返回 `-1` |

**示例**
```python
account = StockAccount('1000000365')
cancel_result = xt_trader.cancel_order_stock_sysid(
    account, xtconstant.SH_MARKET, "100"
)
```

---

### cancel_order_stock_async — 股票异步撤单（按订单编号）

**函数签名**
```python
xt_trader.cancel_order_stock_async(account, order_id)
```

**说明**

根据本地订单编号对委托进行异步撤单操作，立即返回撤单请求序号。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| order_id | int | ✅ | 下单接口返回的订单编号；期货使用 `order.order_sysid` |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回大于 `0` 的撤单请求序号；失败返回 `-1` |

**备注**
- 撤单失败时通过 `on_cancel_error` 推送失败信息

**示例**
```python
account = StockAccount('1000000365')
cancel_result = xt_trader.cancel_order_stock_async(account, order_id)
```

---

### cancel_order_stock_sysid_async — 股票异步撤单（按柜台合同编号）

**函数签名**
```python
xt_trader.cancel_order_stock_sysid_async(account, market, order_sysid)
```

**说明**

根据券商柜台返回的合同编号对委托进行异步撤单操作。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| market | int | ✅ | 交易市场 |
| order_sysid | str | ✅ | 券商柜台的合同编号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回大于 `0` 的撤单请求序号；失败返回 `-1` |

**备注**
- 撤单失败时通过 `on_cancel_error` 推送失败信息

**示例**
```python
account = StockAccount('1000000365')
cancel_result = xt_trader.cancel_order_stock_sysid_async(
    account, xtconstant.SH_MARKET, "100"
)
```

---

### fund_transfer — 资金划拨

**函数签名**
```python
xt_trader.fund_transfer(account, transfer_direction, price)
```

**说明**

在普通柜台与极速柜台之间，或上海节点与深圳节点之间进行资金划拨。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| transfer_direction | int | ✅ | 划拨方向，见数据字典 `transfer_direction` |
| price | float | ✅ | 划拨金额 |

**返回格式**

```python
(success, msg)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 划拨操作是否成功 |
| msg | str | 反馈信息 |

---

### sync_transaction_from_external — 外部交易数据录入

**函数签名**
```python
xt_trader.sync_transaction_from_external(operation, data_type, account, deal_list)
```

**说明**

将外部成交数据录入系统，支持增加、更新、替换、删除操作。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| operation | str | ✅ | 操作类型：`"ADD"`、`"UPDATE"`、`"REPLACE"`、`"DELETE"` |
| data_type | str | ✅ | 数据类型，目前支持 `"DEAL"` |
| account | StockAccount | ✅ | 资金账号 |
| deal_list | list | ✅ | 成交列表，每项为 Deal 成交对象的参数字典，键名参考官网数据字典，大小写保持一致 |

**返回格式**

| 类型 | 说明 |
|------|------|
| dict | 结果反馈信息 |

**示例**
```python
deal_list = [
    {
        'm_strExchangeID': 'SF',
        'm_strInstrumentID': 'ag2407',
        'm_strTradeID': '123456',
        'm_strOrderSysID': '1234566',
        'm_dPrice': 7600,
        'm_nVolume': 1,
        'm_strTradeDate': '20240627'
    }
]
resp = xt_trader.sync_transaction_from_external('ADD', 'DEAL', acc, deal_list)
print(resp)
# 成功：{'msg': 'sync transaction from external success'}
# 失败：{'error': {'msg': '[0-0: invalid operation type: ADDD], '}}
```

---

## 三、股票查询接口

---

### query_stock_asset — 资产查询

**函数签名**
```python
xt_trader.query_stock_asset(account)
```

**说明**

查询指定资金账号的股票资产信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| XtAsset | 资产对象，查询失败返回 `None` |

**XtAsset 常用字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| cash | float | 可用资金 |
| frozen_cash | float | 冻结资金 |
| market_value | float | 持仓市值 |
| total_asset | float | 总资产 |

**示例**
```python
account = StockAccount('1000000365')
asset = xt_trader.query_stock_asset(account)
if asset:
    print("可用资金:", asset.cash)
```

---

### query_stock_orders — 委托查询

**函数签名**
```python
xt_trader.query_stock_orders(account, cancelable_only=False)
```

**说明**

查询当日所有委托记录，可选仅查询可撤委托。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| account | StockAccount | ✅ | — | 资金账号 |
| cancelable_only | bool | ❌ | `False` | `True`：仅返回可撤委托；`False`：返回全部委托 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list[XtOrder] | 委托对象列表 |

**XtOrder 常用字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| stock_code | str | 证券代码 |
| order_id | int | 订单编号 |
| order_sysid | str | 柜台合同编号 |
| order_time | int | 报单时间 |
| order_type | int | 委托类型 |
| order_volume | int | 委托数量 |
| price_type | int | 报价类型 |
| price | float | 委托价格 |
| traded_volume | int | 成交数量 |
| traded_price | float | 成交均价 |
| order_status | int | 委托状态，见数据字典 `order_status` |
| status_msg | str | 委托状态描述 |
| strategy_name | str | 策略名称 |
| order_remark | str | 委托备注 |
| direction | int | 多空方向（期货） |
| offset_flag | int | 交易操作（开/平仓） |

**示例**
```python
account = StockAccount('1000000365')
orders = xt_trader.query_stock_orders(account, False)
print("委托数量:", len(orders))
```

---

### query_stock_order — 单笔委托查询

**函数签名**
```python
xt_trader.query_stock_order(account, order_id)
```

**说明**

根据订单编号查询单笔委托详情。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| order_id | int | ✅ | 订单编号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| XtOrder | 委托对象，查询失败返回 `None` |

**示例**
```python
order = xt_trader.query_stock_order(account, order_id)
if order:
    print("订单编号:", order.order_id)
```

---

### query_stock_trades — 成交查询

**函数签名**
```python
xt_trader.query_stock_trades(account)
```

**说明**

查询当日所有成交记录。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list[XtTrade] | 成交对象列表 |

**XtTrade 常用字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| stock_code | str | 证券代码 |
| order_id | int | 订单编号 |
| traded_id | str | 成交编号 |
| traded_time | int | 成交时间 |
| traded_price | float | 成交价格 |
| traded_volume | int | 成交数量 |
| traded_amount | float | 成交金额 |
| order_type | int | 委托类型 |
| direction | int | 多空方向（期货） |
| offset_flag | int | 交易操作（开/平仓） |

**示例**
```python
account = StockAccount('1000000365')
trades = xt_trader.query_stock_trades(account)
if trades:
    print(trades[-1].stock_code, trades[-1].traded_volume, trades[-1].traded_price)
```

---

### query_stock_positions — 持仓查询（全部）

**函数签名**
```python
xt_trader.query_stock_positions(account)
```

**说明**

查询当日所有持仓记录。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list[XtPosition] | 持仓对象列表 |

**XtPosition 常用字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| stock_code | str | 证券代码 |
| volume | int | 持仓数量 |
| can_use_volume | int | 可用数量 |
| open_price | float | 开仓价 |
| avg_price | float | 成本价 |
| market_value | float | 市值 |
| on_road_volume | int | 在途数量 |
| yesterday_volume | int | 昨日持仓 |
| direction | int | 多空方向（期货） |

**示例**
```python
account = StockAccount('1000000365')
positions = xt_trader.query_stock_positions(account)
if positions:
    print(positions[-1].account_id, positions[-1].stock_code, positions[-1].volume)
```

---

### query_stock_position — 持仓查询（单只）

**函数签名**
```python
xt_trader.query_stock_position(account, stock_code)
```

**说明**

根据证券代码查询对应持仓详情。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |
| stock_code | str | ✅ | 证券代码 |

**返回格式**

| 类型 | 说明 |
|------|------|
| XtPosition | 持仓对象，无持仓时返回 `None` |

**示例**
```python
position = xt_trader.query_stock_position(account, '600000.SH')
if position:
    print(position.volume)
```

---

### query_position_statistics — 期货持仓统计查询

**函数签名**
```python
xt_trader.query_position_statistics(account)
```

**说明**

查询期货账号的持仓统计信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 期货资金账号，账号类型需为 `'FUTURE'` |

**返回格式**

| 类型 | 说明 |
|------|------|
| list | 期货持仓统计列表 |

**示例**
```python
account = StockAccount('1000000365', 'FUTURE')
positions = xt_trader.query_position_statistics(account)
```

---

## 四、信用查询接口

---

### query_credit_detail — 信用资产查询

**函数签名**
```python
xt_trader.query_credit_detail(account)
```

**说明**

查询信用账号的资产详情，包含融资融券相关信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号，账号类型需为 `'CREDIT'` |

**返回格式**

| 类型 | 说明 |
|------|------|
| XtCreditDetail | 信用资产对象 |

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
datas = xt_trader.query_credit_detail(account)
```

---

### query_stk_compacts — 负债合约查询

**函数签名**
```python
xt_trader.query_stk_compacts(account)
```

**说明**

查询信用账号的负债合约列表。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list | 负债合约列表 |

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
datas = xt_trader.query_stk_compacts(account)
```

---

### query_credit_subjects — 融资融券标的查询

**函数签名**
```python
xt_trader.query_credit_subjects(account)
```

**说明**

查询信用账号可进行融资融券操作的标的列表。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list | 融资融券标的列表 |

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
datas = xt_trader.query_credit_subjects(account)
```

---

### query_credit_slo_code — 可融券数据查询

**函数签名**
```python
xt_trader.query_credit_slo_code(account)
```

**说明**

查询信用账号当前可融券的证券列表及数量。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list | 可融券数据列表 |

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
datas = xt_trader.query_credit_slo_code(account)
```

---

### query_credit_assure — 标的担保品查询

**函数签名**
```python
xt_trader.query_credit_assure(account)
```

**说明**

查询信用账号对应的标的担保品列表。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号 |

**返回格式**

| 类型 | 说明 |
|------|------|
| list / None | 担保品列表；查询失败或列表为空时返回 `None` |

**备注**
- 返回 `None` 表示查询失败或标的担保品列表为空

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
datas = xt_trader.query_credit_assure(account)
```

---

## 五、其他查询接口

---

### query_new_purchase_limit — 新股申购额度查询

**函数签名**
```python
xt_trader.query_new_purchase_limit(account)
```

**说明**

查询指定资金账号的新股申购额度。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

```python
dict { type: number }
# 例如：{'KCB': 18000, 'SH': 10000, 'SZ': 8000}
```

| 键 | 说明 |
|----|------|
| `KCB` | 科创板可申购股数 |
| `SH` | 上海市场可申购股数 |
| `SZ` | 深圳市场可申购股数 |

**备注**
- 数据仅代表股票申购额度，债券申购额度固定为 10000 张

---

### query_ipo_data — 当日新股信息查询

**函数签名**
```python
xt_trader.query_ipo_data()
```

**说明**

查询当日新股新债申购信息。

**输入参数**

无。

**返回格式**

```python
dict { stock_code: info }
```

**info 字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | 品种名称 |
| type | str | 品种类型：`'STOCK'`（股票）、`'BOND'`（债券） |
| minPurchaseNum | int | 最小申购额度（股/张） |
| maxPurchaseNum | int | 最大申购额度（股/张） |
| purchaseDate | str | 申购日期，格式 `'YYYYMMDD'` |
| issuePrice | float | 发行价 |

**示例**
```python
ipo_data = xt_trader.query_ipo_data()
# 返回示例：
# {
#   '301208.SZ': {'name': '中亦科技', 'type': 'STOCK', 'maxPurchaseNum': 16500,
#                 'minPurchaseNum': 500, 'purchaseDate': '20220627', 'issuePrice': 46.06},
#   '754810.SH': {'name': '丰山发债', 'type': 'BOND', 'maxPurchaseNum': 10000,
#                 'minPurchaseNum': 10, 'purchaseDate': '20220627', 'issuePrice': 100.0}
# }
```

---

### query_account_infos — 账号信息查询

**函数签名**
```python
xt_trader.query_account_infos()
```

**说明**

查询当前连接的所有资金账号信息。

**输入参数**

无。

**返回格式**

| 类型 | 说明 |
|------|------|
| list[XtAccountInfo] | 账号信息列表 |

---

### query_account_status — 账号状态查询

**函数签名**
```python
xt_trader.query_account_status()
```

**说明**

查询所有账号的当前状态。

**输入参数**

无。

**返回格式**

| 类型 | 说明 |
|------|------|
| list[XtAccountStatus] | 账号状态列表 |

**XtAccountStatus 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| account_type | int | 账号类型 |
| status | int | 账号状态，见数据字典 `account_status` |

---

### query_com_fund — 普通柜台资金查询

**函数签名**
```python
xt_trader.query_com_fund(account)
```

**说明**

划拨业务场景下，查询普通柜台的资金信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

```python
dict {
    'success': bool,
    'error': str,
    'currentBalance': float,   # 当前余额
    'enableBalance': float,    # 可用余额
    'fetchBalance': float,     # 可取金额
    'interest': float,         # 待入账利息
    'assetBalance': float,     # 总资产
    'fetchCash': float,        # 可取现金
    'marketValue': float,      # 市值
    'debt': float              # 负债
}
```

---

### query_com_position — 普通柜台持仓查询

**函数签名**
```python
xt_trader.query_com_position(account)
```

**说明**

划拨业务场景下，查询普通柜台的持仓信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

```python
list [
    {
        'success': bool,
        'error': str,
        'stockAccount': str,      # 股东号
        'exchangeType': str,      # 交易市场
        'stockCode': str,         # 证券代码
        'stockName': str,         # 证券名称
        'totalAmt': float,        # 总量
        'enableAmount': float,    # 可用量
        'lastPrice': float,       # 最新价
        'costPrice': float,       # 成本价
        'income': float,          # 盈亏
        'incomeRate': float,      # 盈亏比例
        'marketValue': float,     # 市值
        'costBalance': float,     # 成本总额
        'bsOnTheWayVol': int,     # 买卖在途量
        'prEnableVol': int        # 申赎可用量
    }
]
```

---

### export_data — 通用数据导出

**函数签名**
```python
xt_trader.export_data(account, result_path, data_type, start_time=None, end_time=None, user_param={})
```

**说明**

将指定类型的交易数据导出为 CSV 文件。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| account | StockAccount | ✅ | — | 资金账号 |
| result_path | str | ✅ | — | 导出路径，含文件名及 `.csv` 后缀，如 `'C:\\Users\\Desktop\\deal.csv'` |
| data_type | str | ✅ | — | 数据类型，如 `'deal'` |
| start_time | str | ❌ | `None` | 开始时间 |
| end_time | str | ❌ | `None` | 结束时间 |
| user_param | dict | ❌ | `{}` | 用户自定义参数 |

**返回格式**

| 类型 | 说明 |
|------|------|
| dict | 结果反馈信息 |

**示例**
```python
resp = xt_trader.export_data(acc, 'C:\\Users\\Desktop\\deal.csv', 'deal')
print(resp)
# 成功：{'msg': 'export success'}
# 失败：{'error': {'errorMsg': 'can not find account info, ...'}}
```

---

### query_data — 通用数据查询

**函数签名**
```python
xt_trader.query_data(account, result_path, data_type, start_time=None, end_time=None, user_param={})
```

**说明**

通用数据查询接口，内部调用 `export_data` 导出数据后读取内容，读取完毕后自动删除临时文件。

**输入参数**

参数含义与 `export_data` 完全相同。

**返回格式**

| 类型 | 说明 |
|------|------|
| dict / pd.DataFrame | 成功返回数据内容；失败返回包含 `error` 键的 dict |

**示例**
```python
data = xt_trader.query_data(acc, 'C:\\Users\\Desktop\\deal.csv', 'deal')
print(data)
# 成功返回 DataFrame，失败返回 {'error': {'errorMsg': '...'}}
```

---

## 六、约券相关接口

---

### smt_query_quoter — 券源行情查询

**函数签名**
```python
xt_trader.smt_query_quoter(account)
```

**说明**

查询当前可用的券源行情信息。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 资金账号 |

**返回格式**

```python
list [quoter_dict, ...]
```

**quoter 字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功 |
| error | str | 错误信息 |
| finType | str | 金融品种 |
| stockType | str | 证券类型 |
| date | int | 期限天数 |
| code | str | 证券代码 |
| codeName | str | 证券名称 |
| exchangeType | str | 市场 |
| fsmpOccupedRate | float | 资券占用利率 |
| fineRate | float | 罚息利率 |
| fsmpreendRate | float | 资券提前归还利率 |
| usedRate | float | 资券使用利率 |
| unUusedRate | float | 资券占用未使用利率 |
| initDate | int | 交易日期 |
| endDate | int | 到期日期 |
| enableSloAmountT0 | float | T+0 可融券数量 |
| enableSloAmountT3 | float | T+3 可融券数量 |
| srcGroupId | str | 来源组编号 |
| applyMode | str | 资券申请方式：`"1"` 库存券，`"2"` 专项券 |
| lowDate | int | 最低期限天数 |

---

### smt_negotiate_order_async — 库存券约券申请

**函数签名**
```python
xt_trader.smt_negotiate_order_async(account, src_group_id, order_code, date, amount, apply_rate, dict_param={})
```

**说明**

发起库存券约券申请的异步接口，申请结果通过 `on_smt_appointment_async_response` 回调推送。

**输入参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| account | StockAccount | ✅ | — | 信用资金账号 |
| src_group_id | str | ✅ | — | 来源组编号（从 `smt_query_quoter` 返回的 `srcGroupId` 获取） |
| order_code | str | ✅ | — | 证券代码，如 `'600000.SH'` |
| date | int | ✅ | — | 期限天数 |
| amount | int | ✅ | — | 委托数量 |
| apply_rate | float | ✅ | — | 资券申请利率 |
| dict_param | dict | ❌ | `{}` | 可选扩展参数：`subFareRate`（提前归还利率）、`fineRate`（罚息利率） |

**返回格式**

| 类型 | 说明 |
|------|------|
| int | 成功返回大于 `0` 的请求序号 `seq`；失败返回 `-1` |

**示例**
```python
account = StockAccount('1000008', 'CREDIT')
dict_param = {'subFareRate': 0.1, 'fineRate': 0.1}
seq = xt_trader.smt_negotiate_order_async(
    account, '', '000001.SZ', 7, 100, 0.2, dict_param
)
```

---

### smt_query_compact — 约券合约查询

**函数签名**
```python
xt_trader.smt_query_compact(account)
```

**说明**

查询当前账号的约券合约列表。

**输入参数**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| account | StockAccount | ✅ | 信用资金账号 |

**返回格式**

```python
list [compact_dict, ...]
```

**compact 字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功 |
| error | str | 错误信息 |
| createDate | int | 创建日期 |
| cashcompactId | str | 头寸合约编号 |
| applyId | str | 资券申请编号 |
| srcGroupId | str | 来源组编号 |
| code | str | 证券代码 |
| codeName | str | 证券名称 |
| date | int | 期限天数 |
| compacAmount | float | 合约数量 |
| compacBalance | float | 合约金额 |
| returnAmount | float | 返还数量 |
| fsmpOccupedRate | float | 资券占用利率 |
| compactInterest | float | 合约利息金额 |
| fineRate | float | 罚息利率 |
| compactStatus | str | 合约状态：`"0"` 未归还，`"1"` 部分归还，`"2"` 提前了结，`"3"` 到期了结，`"4"` 逾期了结，`"5"` 逾期，`"9"` 已作废 |
| validDate | int | 有效日期 |
| usedAmount | float | 已使用数量 |
| usedRate | float | 资券使用利率 |
| postponeTimes | int | 展期次数 |
| postponeStatus | str | 展期状态：`"0"` 未审核，`"1"` 审核通过，`"2"` 已撤销，`"3"` 审核不通过 |
| applyMode | str | 资券申请方式：`"1"` 库存券，`"2"` 专项券 |

**示例**
```python
account = StockAccount('1208970161', 'CREDIT')
compacts = xt_trader.smt_query_compact(account)
```

---

## 七、回调类接口

回调类需继承 `XtQuantTraderCallback` 并重写对应方法，通过 `register_callback` 注册后生效。

```python
class MyXtQuantTraderCallback(XtQuantTraderCallback):
    def on_disconnected(self): ...
    def on_account_status(self, status): ...
    def on_stock_order(self, order): ...
    def on_stock_trade(self, trade): ...
    def on_order_error(self, order_error): ...
    def on_cancel_error(self, cancel_error): ...
    def on_order_stock_async_response(self, response): ...
    def on_smt_appointment_async_response(self, response): ...
```

---

### on_disconnected — 连接断开回调

**函数签名**
```python
def on_disconnected(self)
```

**说明**

与 MiniQMT 连接断开时触发。

**参数**

无。

**返回**

无。

**示例**
```python
def on_disconnected(self):
    print("connection lost")
```

---

### on_account_status — 账号状态推送

**函数签名**
```python
def on_account_status(self, status)
```

**说明**

账号状态发生变化时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| status | XtAccountStatus | 账号状态对象 |

**XtAccountStatus 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| account_type | int | 账号类型 |
| status | int | 账号状态，见数据字典 `account_status` |

**示例**
```python
def on_account_status(self, status):
    print(status.account_id, status.account_type, status.status)
```

---

### on_stock_order — 委托信息推送

**函数签名**
```python
def on_stock_order(self, order)
```

**说明**

委托状态发生变化时推送（报单、成交、撤单等）。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| order | XtOrder | 委托对象，字段见 `query_stock_orders` 返回格式 |

**示例**
```python
def on_stock_order(self, order):
    print(order.stock_code, order.order_status, order.order_sysid)
```

---

### on_stock_trade — 成交信息推送

**函数签名**
```python
def on_stock_trade(self, trade)
```

**说明**

发生成交时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| trade | XtTrade | 成交对象，字段见 `query_stock_trades` 返回格式 |

**示例**
```python
def on_stock_trade(self, trade):
    print(trade.account_id, trade.stock_code, trade.order_id)
```

---

### on_order_error — 下单失败推送

**函数签名**
```python
def on_order_error(self, order_error)
```

**说明**

异步下单失败时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| order_error | XtOrderError | 下单失败对象 |

**XtOrderError 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | int | 订单编号 |
| error_id | int | 错误编号 |
| error_msg | str | 错误信息 |

**示例**
```python
def on_order_error(self, order_error):
    print(order_error.order_id, order_error.error_id, order_error.error_msg)
```

---

### on_cancel_error — 撤单失败推送

**函数签名**
```python
def on_cancel_error(self, cancel_error)
```

**说明**

异步撤单失败时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| cancel_error | XtCancelError | 撤单失败对象 |

**XtCancelError 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | int | 订单编号 |
| error_id | int | 错误编号 |
| error_msg | str | 错误信息 |

**示例**
```python
def on_cancel_error(self, cancel_error):
    print(cancel_error.order_id, cancel_error.error_id, cancel_error.error_msg)
```

---

### on_order_stock_async_response — 异步下单回报推送

**函数签名**
```python
def on_order_stock_async_response(self, response)
```

**说明**

调用 `order_stock_async` 后，收到委托回报时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| response | XtOrderResponse | 异步下单回报对象 |

**XtOrderResponse 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | str | 资金账号 |
| order_id | int | 订单编号 |
| seq | int | 下单请求序号，与 `order_stock_async` 返回值对应 |

**示例**
```python
def on_order_stock_async_response(self, response):
    print(response.account_id, response.order_id, response.seq)
```

---

### on_smt_appointment_async_response — 约券异步接口回报推送

**函数签名**
```python
def on_smt_appointment_async_response(self, response)
```

**说明**

调用 `smt_negotiate_order_async` 后，收到约券申请回报时推送。

**参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| response | XtSmtAppointmentResponse | 约券异步回报对象 |

**XtSmtAppointmentResponse 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| seq | int | 异步请求序号，与 `smt_negotiate_order_async` 返回值对应 |
| success | bool | 申请是否成功 |
| msg | str | 反馈信息 |
| apply_id | str | 申请成功时返回资券申请编号，否则返回 `-1` |

**示例**
```python
def on_smt_appointment_async_response(self, response):
    print(response.account_id, response.order_sysid,
          response.error_id, response.error_msg, response.seq)
```

---

## 附录 A：数据字典

### 交易市场（market）

| 常量 | 说明 |
|------|------|
| `xtconstant.SH_MARKET` | 上交所 |
| `xtconstant.SZ_MARKET` | 深交所 |
| `xtconstant.MARKET_ENUM_BEIJING` | 北交所 |
| `xtconstant.MARKET_ENUM_SHANGHAI_HONGKONG_STOCK` | 沪港通 |
| `xtconstant.MARKET_ENUM_SHENZHEN_HONGKONG_STOCK` | 深港通 |
| `xtconstant.MARKET_ENUM_SHANGHAI_FUTURE` | 上期所 |
| `xtconstant.MARKET_ENUM_DALIANG_FUTURE` | 大商所 |
| `xtconstant.MARKET_ENUM_ZHENGZHOU_FUTURE` | 郑商所 |
| `xtconstant.MARKET_ENUM_INDEX_FUTURE` | 中金所 |
| `xtconstant.MARKET_ENUM_INTL_ENERGY_FUTURE` | 能源中心 |
| `xtconstant.MARKET_ENUM_GUANGZHOU_FUTURE` | 广期所 |
| `xtconstant.MARKET_ENUM_SHANGHAI_STOCK_OPTION` | 上海期权 |
| `xtconstant.MARKET_ENUM_SHENZHEN_STOCK_OPTION` | 深证期权 |

---

### 账号类型（account_type）

| 常量 | 说明 |
|------|------|
| `xtconstant.SECURITY_ACCOUNT` | 股票 |
| `xtconstant.CREDIT_ACCOUNT` | 信用 |
| `xtconstant.FUTURE_ACCOUNT` | 期货 |
| `xtconstant.FUTURE_OPTION_ACCOUNT` | 期货期权 |
| `xtconstant.STOCK_OPTION_ACCOUNT` | 股票期权 |
| `xtconstant.HUGANGTONG_ACCOUNT` | 沪港通 |
| `xtconstant.SHENGANGTONG_ACCOUNT` | 深港通 |

---

### 委托类型（order_type）

**股票**

| 常量 | 说明 |
|------|------|
| `xtconstant.STOCK_BUY` | 买入 |
| `xtconstant.STOCK_SELL` | 卖出 |

**信用**

| 常量 | 说明 |
|------|------|
| `xtconstant.CREDIT_BUY` | 担保品买入 |
| `xtconstant.CREDIT_SELL` | 担保品卖出 |
| `xtconstant.CREDIT_FIN_BUY` | 融资买入 |
| `xtconstant.CREDIT_SLO_SELL` | 融券卖出 |
| `xtconstant.CREDIT_BUY_SECU_REPAY` | 买券还券 |
| `xtconstant.CREDIT_DIRECT_SECU_REPAY` | 直接还券 |
| `xtconstant.CREDIT_SELL_SECU_REPAY` | 卖券还款 |
| `xtconstant.CREDIT_DIRECT_CASH_REPAY` | 直接还款 |
| `xtconstant.CREDIT_FIN_BUY_SPECIAL` | 专项融资买入 |
| `xtconstant.CREDIT_SLO_SELL_SPECIAL` | 专项融券卖出 |

**期货（六键风格）**

| 常量 | 说明 |
|------|------|
| `xtconstant.FUTURE_OPEN_LONG` | 开多 |
| `xtconstant.FUTURE_CLOSE_LONG_HISTORY` | 平昨多 |
| `xtconstant.FUTURE_CLOSE_LONG_TODAY` | 平今多 |
| `xtconstant.FUTURE_OPEN_SHORT` | 开空 |
| `xtconstant.FUTURE_CLOSE_SHORT_HISTORY` | 平昨空 |
| `xtconstant.FUTURE_CLOSE_SHORT_TODAY` | 平今空 |

**期货（四键风格）**

| 常量 | 说明 |
|------|------|
| `xtconstant.FUTURE_CLOSE_LONG_TODAY_FIRST` | 平多，优先平今 |
| `xtconstant.FUTURE_CLOSE_LONG_HISTORY_FIRST` | 平多，优先平昨 |
| `xtconstant.FUTURE_CLOSE_SHORT_TODAY_FIRST` | 平空，优先平今 |
| `xtconstant.FUTURE_CLOSE_SHORT_HISTORY_FIRST` | 平空，优先平昨 |

**期货（两键风格）**

| 常量 | 说明 |
|------|------|
| `xtconstant.FUTURE_CLOSE_LONG_TODAY_HISTORY_THEN_OPEN_SHORT` | 卖出，优先平多（平今优先），余量开空 |
| `xtconstant.FUTURE_CLOSE_LONG_HISTORY_TODAY_THEN_OPEN_SHORT` | 卖出，优先平多（平昨优先），余量开空 |
| `xtconstant.FUTURE_CLOSE_SHORT_TODAY_HISTORY_THEN_OPEN_LONG` | 买入，优先平空（平今优先），余量开多 |
| `xtconstant.FUTURE_CLOSE_SHORT_HISTORY_TODAY_THEN_OPEN_LONG` | 买入，优先平空（平昨优先），余量开多 |
| `xtconstant.FUTURE_OPEN` | 买入，不优先平仓 |
| `xtconstant.FUTURE_CLOSE` | 卖出，不优先平仓 |

**股票期权**

| 常量 | 说明 |
|------|------|
| `xtconstant.STOCK_OPTION_BUY_OPEN` | 买入开仓 |
| `xtconstant.STOCK_OPTION_SELL_CLOSE` | 卖出平仓 |
| `xtconstant.STOCK_OPTION_SELL_OPEN` | 卖出开仓 |
| `xtconstant.STOCK_OPTION_BUY_CLOSE` | 买入平仓 |
| `xtconstant.STOCK_OPTION_COVERED_OPEN` | 备兑开仓 |
| `xtconstant.STOCK_OPTION_COVERED_CLOSE` | 备兑平仓 |
| `xtconstant.STOCK_OPTION_CALL_EXERCISE` | 认购行权 |
| `xtconstant.STOCK_OPTION_PUT_EXERCISE` | 认沽行权 |
| `xtconstant.STOCK_OPTION_SECU_LOCK` | 证券锁定 |
| `xtconstant.STOCK_OPTION_SECU_UNLOCK` | 证券解锁 |

**ETF 申赎**

| 常量 | 说明 |
|------|------|
| `xtconstant.ETF_PURCHASE` | 申购 |
| `xtconstant.ETF_REDEMPTION` | 赎回 |

---

### 报价类型（price_type）

> ⚠️ 市价类型仅在实盘环境中生效，模拟环境不支持市价报单。

| 常量 | 说明 |
|------|------|
| `xtconstant.FIX_PRICE` | 指定价（限价） |
| `xtconstant.LATEST_PRICE` | 最新价 |
| `xtconstant.MARKET_BEST` | 市价最优价（郑商所期货） |
| `xtconstant.MARKET_CANCEL` | 市价即成剩撤（大商所期货） |
| `xtconstant.MARKET_CANCEL_ALL` | 市价全额成交或撤（大商所期货） |
| `xtconstant.MARKET_CANCEL_1` | 市价最优一档即成剩撤（中金所期货） |
| `xtconstant.MARKET_CANCEL_5` | 市价最优五档即成剩撤（中金所期货） |
| `xtconstant.MARKET_CONVERT_1` | 市价最优一档即成剩转（中金所期货） |
| `xtconstant.MARKET_CONVERT_5` | 市价最优五档即成剩转（中金所期货） |
| `xtconstant.MARKET_SH_CONVERT_5_CANCEL` | 最优五档即时成交剩余撤销（上交所/北交所股票） |
| `xtconstant.MARKET_SH_CONVERT_5_LIMIT` | 最优五档即时成交剩转限价（上交所/北交所股票） |
| `xtconstant.MARKET_PEER_PRICE_FIRST` | 对手方最优价格委托（上交所/深交所股票期权） |
| `xtconstant.MARKET_MINE_PRICE_FIRST` | 本方最优价格委托（上交所/深交所股票期权） |
| `xtconstant.MARKET_SZ_INSTBUSI_RESTCANCEL` | 即时成交剩余撤销（深交所股票期权） |
| `xtconstant.MARKET_SZ_CONVERT_5_CANCEL` | 最优五档即时成交剩余撤销（深交所股票期权） |
| `xtconstant.MARKET_SZ_FULL_OR_CANCEL` | 全额成交或撤销（深交所股票期权） |

---

### 委托状态（order_status）

| 常量 | 值 | 说明 |
|------|----|------|
| `xtconstant.ORDER_UNREPORTED` | 48 | 未报 |
| `xtconstant.ORDER_WAIT_REPORTING` | 49 | 待报 |
| `xtconstant.ORDER_REPORTED` | 50 | 已报 |
| `xtconstant.ORDER_REPORTED_CANCEL` | 51 | 已报待撤 |
| `xtconstant.ORDER_PARTSUCC_CANCEL` | 52 | 部成待撤 |
| `xtconstant.ORDER_PART_CANCEL` | 53 | 部撤（部分成交，剩余已撤） |
| `xtconstant.ORDER_CANCELED` | 54 | 已撤 |
| `xtconstant.ORDER_PART_SUCC` | 55 | 部成（部分成交，剩余待成交） |
| `xtconstant.ORDER_SUCCEEDED` | 56 | 已成 |
| `xtconstant.ORDER_JUNK` | 57 | 废单 |
| `xtconstant.ORDER_UNKNOWN` | 255 | 未知 |

---

### 账号状态（account_status）

| 常量 | 值 | 说明 |
|------|----|------|
| `xtconstant.ACCOUNT_STATUS_INVALID` | -1 | 无效 |
| `xtconstant.ACCOUNT_STATUS_OK` | 0 | 正常 |
| `xtconstant.ACCOUNT_STATUS_WAITING_LOGIN` | 1 | 连接中 |
| `xtconstant.ACCOUNT_STATUSING` | 2 | 登陆中 |
| `xtconstant.ACCOUNT_STATUS_FAIL` | 3 | 失败 |
| `xtconstant.ACCOUNT_STATUS_INITING` | 4 | 初始化中 |
| `xtconstant.ACCOUNT_STATUS_CORRECTING` | 5 | 数据刷新校正中 |
| `xtconstant.ACCOUNT_STATUS_CLOSED` | 6 | 收盘后 |
| `xtconstant.ACCOUNT_STATUS_ASSIS_FAIL` | 7 | 穿透副链接断开 |
| `xtconstant.ACCOUNT_STATUS_DISABLEBYSYS` | 8 | 系统停用（密码错误超限） |
| `xtconstant.ACCOUNT_STATUS_DISABLEBYUSER` | 9 | 用户停用 |

---

### 划拨方向（transfer_direction）

| 常量 | 值 | 说明 |
|------|----|------|
| `xtconstant.FUNDS_TRANSFER_NORMAL_TO_SPEED` | 510 | 普通柜台 → 极速柜台 |
| `xtconstant.FUNDS_TRANSFER_SPEED_TO_NORMAL` | 511 | 极速柜台 → 普通柜台 |
| `xtconstant.NODE_FUNDS_TRANSFER_SH_TO_SZ` | 512 | 上海节点 → 深圳节点 |
| `xtconstant.NODE_FUNDS_TRANSFER_SZ_TO_SH` | 513 | 深圳节点 → 上海节点 |

---

### 多空方向（direction）

| 常量 | 值 | 说明 |
|------|----|------|
| `xtconstant.DIRECTION_FLAG_LONG` | 48 | 多 |
| `xtconstant.DIRECTION_FLAG_SHORT` | 49 | 空 |

---

### 交易操作（offset_flag）

| 常量 | 值 | 说明 |
|------|----|------|
| `xtconstant.OFFSET_FLAG_OPEN` | 48 | 买入 / 开仓 |
| `xtconstant.OFFSET_FLAG_CLOSE` | 49 | 卖出 / 平仓 |
| `xtconstant.OFFSET_FLAG_FORCECLOSE` | 50 | 强平 |
| `xtconstant.OFFSET_FLAG_CLOSETODAY` | 51 | 平今 |
| `xtconstant.OFFSET_FLAG_ClOSEYESTERDAY` | 52 | 平昨 |
| `xtconstant.OFFSET_FLAG_FORCEOFF` | 53 | 强减 |
| `xtconstant.OFFSET_FLAG_LOCALFORCECLOSE` | 54 | 本地强平 |

---

## 附录 B：快速入门完整示例

```python
# coding=utf-8
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant


class MyXtQuantTraderCallback(XtQuantTraderCallback):
    def on_disconnected(self):
        print("connection lost")

    def on_stock_order(self, order):
        print("on order callback:")
        print(order.stock_code, order.order_status, order.order_sysid)

    def on_stock_trade(self, trade):
        print("on trade callback")
        print(trade.account_id, trade.stock_code, trade.order_id)

    def on_order_error(self, order_error):
        print("on order_error callback")
        print(order_error.order_id, order_error.error_id, order_error.error_msg)

    def on_cancel_error(self, cancel_error):
        print("on cancel_error callback")
        print(cancel_error.order_id, cancel_error.error_id, cancel_error.error_msg)

    def on_order_stock_async_response(self, response):
        print("on_order_stock_async_response")
        print(response.account_id, response.order_id, response.seq)

    def on_account_status(self, status):
        print("on_account_status")
        print(status.account_id, status.account_type, status.status)


if __name__ == "__main__":
    # 1. 初始化
    path = 'D:\\迅投极速交易终端 睿智融科版\\userdata_mini'
    session_id = 123456
    xt_trader = XtQuantTrader(path, session_id)

    # 2. 注册回调
    callback = MyXtQuantTraderCallback()
    xt_trader.register_callback(callback)

    # 3. 启动并连接
    xt_trader.start()
    connect_result = xt_trader.connect()
    print("connect:", connect_result)

    # 4. 订阅账号
    acc = StockAccount('1000000365')
    subscribe_result = xt_trader.subscribe(acc)
    print("subscribe:", subscribe_result)

    # 5. 下单
    stock_code = '600000.SH'
    order_id = xt_trader.order_stock(
        acc, stock_code, xtconstant.STOCK_BUY,
        200, xtconstant.FIX_PRICE, 10.5,
        'strategy_name', 'remark'
    )
    print("order_id:", order_id)

    # 6. 撤单
    cancel_result = xt_trader.cancel_order_stock(acc, order_id)
    print("cancel:", cancel_result)

    # 7. 查询
    asset = xt_trader.query_stock_asset(acc)
    if asset:
        print("cash:", asset.cash)

    orders = xt_trader.query_stock_orders(acc)
    print("orders count:", len(orders))

    positions = xt_trader.query_stock_positions(acc)
    print("positions count:", len(positions))

    # 8. 阻塞等待推送
    xt_trader.run_forever()
```
