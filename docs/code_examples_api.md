# XtQuant 完整实例代码

> 来源：https://dict.thinktrader.net/nativeApi/code_examples.html?id=dqamF2

---

## 行情示例

### 获取行情示例

```

### 连接VIP服务器

```

### 连接指定服务器

```

### 指定初始化行情连接范围

```python

if 1:
    from xtquant import xtdatacenter as xtdc

    ## 设置数据目录
    xtdc.set_data_home_dir('data')

    ## 设置token
    token = 你的token
    xtdc.set_token(token)

    ## 限定行情站点的优选范围
    opt_list = [
        '115.231.218.73:55310',
        '115.231.218.79:55310',
        '42.228.16.210:55300',
        '42.228.16.211:55300',
        '36.99.48.20:55300',
        '36.99.48.21:55300',
    ]
    xtdc.set_allow_optmize_address(opt_list)

    ## 开启指定市场的K线全推
    xtdc.set_kline_mirror_markets(['SH', 'SZ', 'BJ'])

    ## 设置要初始化的市场列表
    init_markets = [
        'SH', 'SZ', 'BJ',
        #'DF', 'GF', 'IF', 'SF', 'ZF', 'INE',
        #'SHO', 'SZO',
    ]
    xtdc.set_init_markets(init_markets)

    ## 初始化xtdc模块
    xtdc.init( = False)

    ## 监听端口
    #xtdc.listen(port = 58620)
    listen_port = xtdc.listen( = (58620, 58650))

    #import code; code.interact(local = locals())

import xtquant.xtdata as xtdata

xtdata.connect( = listen_port)

import code; code.interact( = locals())

```

### 订阅全推数据/下载历史数据

```python

# coding:utf-8
import time

from xtquant import xtdata

code = '600000.SH'

#取全推数据
full_tick = xtdata.get_full_tick([code])
print('全推数据 日线最新值', full_tick)

#下载历史数据 下载接口本身不返回数据
xtdata.download_history_data(code, ='1m', ='20230701')

#订阅最新行情
def callback_func():
    print('回调触发', data)

xtdata.subscribe_quote(code, ='1m', =-1, = callback_func)
data = xtdata.get_market_data(['close'], [code], ='1m', ='20230701')
print('一次性取数据', data)

#死循环 阻塞主线程退出
xtdata.run()

```

### 获取对手价

```python

# 以卖出为例

import pandas as pd
import numpy as np
from xtquant import xtdata

to_do_trade_list = [000001.SZ]
tick = xtdata.get_full_tick(to_do_trade_list)

# 取买一价为对手价，若买一价为0，说明已经跌停，则取最新价
for i in tick:
    fix_price = tick[i][bidPrice][0] if tick[i][bidPrice][0] != 0 else tick[i][lastPrice]
    print(fix_price)
```

```

### 复权计算方式

```python

#coding:utf-8

import numpy as np
import pandas as pd

from xtquant import xtdata

#def gen_divid_ratio(quote_datas, divid_datas):
#    drl = []
#    for qi in range(len(quote_datas)):
#        q = quote_datas.iloc[qi]
#        dr = 1.0
#        for di in range(len(divid_datas)):
#            d = divid_datas.iloc[di]
#            if d.name <= q.name:
#                dr *= d['dr']
#        drl.append(dr)
#    return pd.DataFrame(drl, index = quote_datas.index, columns = quote_datas.columns)

def gen_divid_ratio(, ):
    drl = []
    dr = 1.0
    qi = 0
    qdl = len(quote_datas)
    di = 0
    ddl = len(divid_datas)
    while qi < qdl and di < ddl:
        qd = quote_datas.iloc[qi]
        dd = divid_datas.iloc[di]
        if qd.name >= dd.name:
            dr *= dd['dr']
            di += 1
        if qd.name <= dd.name:
            drl.append(dr)
            qi += 1
    while qi < qdl:
        drl.append(dr)
        qi += 1
    return pd.DataFrame(drl,  = quote_datas.index,  = quote_datas.columns)

def process_forward_ratio(, ):
    drl = gen_divid_ratio(quote_datas, divid_datas)
    drlf = drl / drl.iloc[-1]
    result = (quote_datas * drlf).apply(lambda : round(x, 2))
    return result

def process_backward_ratio(, ):
    drl = gen_divid_ratio(quote_datas, divid_datas)
    result = (quote_datas * drl).apply(lambda : round(x, 2))
    return result

def process_forward(, ):
    quote_datas = quote_datas1.copy()
    def calc_front(, ):
        return ((v - d['interest'] + d['allotPrice'] * d['allotNum'])
            / (1 + d['allotNum'] + d['stockBonus'] + d['stockGift']))
    for qi in range(len(quote_datas)):
        q = quote_datas.iloc[qi]
        for di in range(len(divid_datas)):
            d = divid_datas.iloc[di]
            if d.name <= q.name:
                continue
            q.iloc[0] = calc_front(q.iloc[0], d)
    return quote_datas

def process_backward(, ):
    quote_datas = quote_datas1.copy()
    def calc_back(, ):
        return ((v * (1.0 + d['stockGift'] + d['stockBonus'] + d['allotNum'])
            + d['interest'] - d['allotNum'] * d['allotPrice']))
    for qi in range(len(quote_datas)):
        q = quote_datas.iloc[qi]
        for di in range(len(divid_datas) - 1, -1, -1):
            d = divid_datas.iloc[di]
            if d.name > q.name:
                continue
            q.iloc[0] = calc_back(q.iloc[0], d)
    return quote_datas

#--------------------------------

s = '002594.SZ'

#xtdata.download_history_data(s, '1d', '20100101', '')

dd = xtdata.get_divid_factors(s)
print(dd)

#复权计算用于处理价格字段
field_list = ['open', 'high', 'low', 'close']
datas_ori = xtdata.get_market_data(field_list, [s], '1d',  = 'none')['close'].T
#print(datas_ori)

#等比前复权
datas_forward_ratio = process_forward_ratio(datas_ori, dd)
print('datas_forward_ratio', datas_forward_ratio)

#等比后复权
datas_backward_ratio = process_backward_ratio(datas_ori, dd)
print('datas_backward_ratio', datas_backward_ratio)

#前复权
datas_forward = process_forward(datas_ori, dd)
print('datas_forward', datas_forward)

#后复权
datas_backward = process_backward(datas_ori, dd)
print('datas_backward', datas_backward)

```

### 根据商品期货期权代码获取对应的商品期货合约代码

```python

from xtquant import xtdata

def get_option_underline_code(:) -> :
    
    注意：该函数不适用于股指期货期权与ETF期权
    Todo: 根据商品期权代码获取对应的具体商品期货合约
    Args:
        code:str 期权代码
    Return:
        对应的期货合约代码

    Exchange_dict = {
        SHFE:SF,
        CZCE:ZF,
        DCE:DF,
        INE:INE,
        GFEX:GF
    }
    
    if code.split(.)[-1] not in [v for k,v in Exchange_dict.items()]:
        raise (此函数不支持该交易所合约)
    info = xtdata.get_option_detail_data(code)
    underline_code = info[OptUndlCode] + . + Exchange_dict[info[OptUndlMarket]]

    return underline_code

if __name__ == __main__:

    symbol_code = get_option_underline_code('sc2403C465.INE') # 获取期权合约'sc2403C465.INE'对应的期货合约代码
    print(symbol_code)

```

```python

'sc2403.INE'
```

### 根据指数代码，返回对应的期货合约

```python

from xtquant import xtdata
import re

def get_financial_futures_code_from_index(:) -> :
    
    ToDo:传入指数代码，返回对应的期货合约（当前）
    Args:

    Retuen:
        list: 对应期货合约列表

    financial_futures = xtdata.get_stock_list_in_sector(中金所)
    future_list = []
    pattern = r'[a-zA-Z]{1,2}{3,4}\.[A-Z]{2}'
    for i in financial_futures:
        
        if re.match(pattern,i):
            future_list.append(i)
    ls = []
    for i in future_list:
        _info = xtdata._get_instrument_detail(i)
        _index_code = _info[ExtendInfo]['OptUndlCode'] + . + _info[ExtendInfo]['OptUndlMarket']
        if _index_code == index_code:
            ls.append(i)
    return ls

if __name__ == __main__:
    ls = get_financial_futures_code_from_index(000905.SH)
    print(ls)

```

```

### 高频因子数据共享

```python

#coding:utf-8

import xtquant.invadv as xtia

remote_host = '115.231.218.7'
remote_port = 55300
user_name = '授权账号'
password = '授权账号对应密码'

# 连接云服务
api = xtia.InvAdv()
api.set_remote_addr(remote_host, remote_port)
# 这是总用户  负责上传篮子
api.set_user(user_name, password)
api.connect()

# 可用板块列表
ret_sector_dict = api.get_block_list()
print(f'支持的板块列表:{ret_sector_dict}')

new_dict = {v: k for k, v in ret_sector_dict.items()}
# 创建新的板块
fp_name = '测试投顾C'
if fp_name not in new_dict:
    api.create_block(fp_name)
    print(f'创建{fp_name}表')

# 板块对应代码
codes = {'002594.SZ': 0.009, '300750.SZ': 0.007, '688001.SH': 0.1, '000001.SZ':0.2, '300751.SZ':0.3}

# 获取最新的板块
ret_sector_dict = api.get_block_list()
print(f'支持的板块列表:{ret_sector_dict}')

# 板块权限的设置
for k_msg_id, v in ret_sector_dict.items():
    write_codes = []
    if v == fp_name:
        for code, value in codes.items():
            # code = int(code)
            # if 700000 > code >= 600000:
            #     code = f'{code}.SH'
            # else:
            #     code = '{}.SZ'.format(str(code).rjust(6, '0'))
            write_codes.append(f'{code}|{value}')
        # 上传代码
        api.push_block(k_msg_id, write_codes)

        print(f'表:{fp_name} id:{k_msg_id} {write_codes}')
        print(f'上传结束!')

print('====end====')

```

```python

#coding:utf-8
import time
import json
import os
import xtquant.invadv as xtia

api = xtia.InvAdv()

api.set_remote_addr('115.231.218.7', 55300)
api.set_user('授权账号', '授权账号对应密码')
api.connect()
ret_sector_dict = api.get_block_list()
print(ret_sector_dict)

buy_cur_ji_json_path = r'C:\Users\adminesktop\测试'

while 1:
    # if time.strftime('%H%M%S') > '150000' or time.strftime('%H%M%S') < '091430':
    if 1:
        ret_sector_dict = api.get_block_list()
        for mid, v in ret_sector_dict.items():
            # 是否更新
            sector_gt_list = []
            if v not in ['CESHI2', '新建共享板块3', 'B投顾', '测试投顾信号', '测试投顾信号A']:
                try:
                    if api.check_outdated(mid):
                        basket_list = api.pull_block(mid)
                        print(basket_list)
                        if basket_list == []:
                            continue
                        print(f'板块:{v} 有新的更新, 更新板块!')
                        for s in basket_list:
                            sector_gt_list.append(s[:9])
                        print(f'更新板块:{v} 长度:{len(basket_list)} 内容:{sector_gt_list}')
                        # with open(buy_cur_ji_json_path + os.sep + f'{v}_板块.json', 'w',
                        #           encoding='utf-8') as f:
                        #     json.dump({'选股': sector_gt_list}, f, ensure_ascii=False, indent=4)
                except:
                    pass
    time.sleep(5)

```

```python

# coding:utf-8
import time, datetime, traceback, sys
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant

# 定义一个类 创建类的实例 作为状态的容器
class _a():
    pass

A = _a()
A.bought_list = []
A.hsa = xtdata.get_stock_list_in_sector('沪深A股')

def interact():
    
    import code
    code.InteractiveConsole(=globals()).interact()

xtdata.download_sector_data()

class MyXtQuantTraderCallback():
    def on_disconnected():
        
        连接断开
        :return:

        print(datetime.datetime.now(), '连接断开回调')

    def on_stock_order(, ):
        
        委托回报推送
        :param order: XtOrder对象
        :return:

        print(datetime.datetime.now(), '委托回调 投资备注', order.order_remark)

    def on_stock_trade(, ):
        
        成交变动推送
        :param trade: XtTrade对象
        :return:

        print(datetime.datetime.now(), '成交回调', trade.order_remark, f{trade.offset_flag} 成交价格 {trade.traded_price} 成交数量 {trade.traded_volume})

    def on_order_error(, ):
        
        委托失败推送
        :param order_error:XtOrderError 对象
        :return:

        
        # print(order_error.order_id, order_error.error_id, order_error.error_msg)
        print(f{order_error.order_remark} {order_error.error_msg})

    def on_cancel_error(, ):
        
        撤单失败推送
        :param cancel_error: XtCancelError 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_order_stock_async_response(, ):
        
        异步下单回报推送
        :param response: XtOrderResponse 对象
        :return:

        print(f{response.order_remark})

    def on_cancel_order_stock_async_response(, ):
        
        :param response: XtCancelOrderResponse 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_account_status(, ):
        
        :param response: XtAccountStatus 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

if __name__ == '__main__':
    print(start)
    # 指定客户端所在路径, 券商端指定到 userdata_mini文件夹
    
    path = r'D:\qmt\投研\迅投极速交易终端睿智融科版\userdata'
    # 生成session id 整数类型 同时运行的策略不能重复
    session_id = (time.time())
    xt_trader = XtQuantTrader(path, session_id)
    # 开启主动请求接口的专用线程 开启后在on_stock_xxx回调函数里调用XtQuantTrader.query_xxx函数不会卡住回调线程，但是查询和推送的数据在时序上会变得不确定
    # 详见: http://docs.thinktrader.net/vip/pages/ee0e9b/#开启主动请求接口的专用线程
    # xt_trader.set_relaxed_response_order_enabled(True)

    # 创建资金账号为 800068 的证券账号对象 股票账号为STOCK 信用CREDIT 期货FUTURE
    acc = StockAccount('2000128', 'STOCK')
    # 创建交易回调类对象，并声明接收回调
    callback = MyXtQuantTraderCallback()
    xt_trader.register_callback(callback)
    # 启动交易线程
    xt_trader.start()
    # 建立交易连接，返回0表示连接成功
    connect_result = xt_trader.connect()
    print('建立交易连接，返回0表示连接成功', connect_result)
    # 对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功
    subscribe_result = xt_trader.subscribe(acc)
    print('对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功', subscribe_result)
    #取账号信息
    account_info = xt_trader.query_stock_asset(acc)
    #取可用资金
    available_cash = account_info.m_dCash

    print(acc.account_id, '可用资金', available_cash)
    #查账号持仓
    positions = xt_trader.query_stock_positions(acc)
    #取各品种 总持仓 可用持仓
    position_total_dict = {i.stock_code : i.m_nVolume for i in positions}
    position_available_dict = {i.stock_code : i.m_nCanUseVolume for i in positions}
    print(acc.account_id, '持仓字典', position_total_dict)
    print(acc.account_id, '可用持仓字典', position_available_dict)

    #买入 浦发银行 最新价 两万元
    stock = '600000.SH'
    target_amount = 20000
    full_tick = xtdata.get_full_tick([stock])
    print(f{stock} 全推行情： {full_tick})
    current_price = full_tick[stock]['lastPrice']
    #买入金额 取目标金额 与 可用金额中较小的
    buy_amount = min(target_amount, available_cash)
    #买入数量 取整为100的整数倍
    buy_vol = (buy_amount / current_price / 100) * 100
    print(f{available_cash} 目标买入金额 {target_amount} 买入股数 {buy_vol})
    async_seq = xt_trader.order_stock_async(acc, stock, xtconstant.STOCK_BUY, buy_vol, xtconstant.FIX_PRICE, current_price,
                                            'strategy_name', stock)

    #卖出 500股
    stock = '513130.SH'
    #目标数量
    target_vol = 500
    #可用数量
    available_vol = position_available_dict[stock] if stock in position_available_dict else 0
    #卖出量取目标量与可用量中较小的
    sell_vol = min(target_vol, available_vol)
    print(f{stock} 目标卖出量 {target_vol} 可用数量 {available_vol} 卖出 {sell_vol})
    if sell_vol > 0:
        async_seq = xt_trader.order_stock_async(acc, stock, xtconstant.STOCK_SELL, sell_vol, xtconstant.LATEST_PRICE,
                                                -1,
                                                'strategy_name', stock)
    print(f)
    # 阻塞主线程退出
    xt_trader.run_forever()
    # 如果使用vscode pycharm等本地编辑器 可以进入交互模式 方便调试 （把上一行的run_forever注释掉 否则不会执行到这里）
    interact()

```

### 单股订阅实盘示例

```python

# coding:utf-8
import time, datetime, traceback, sys
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant

# 定义一个类 创建类的实例 作为状态的容器
class _a():
    pass

A = _a()
A.bought_list = []
A.hsa = xtdata.get_stock_list_in_sector('沪深A股')

def interact():
    
    import code
    code.InteractiveConsole(=globals()).interact()

xtdata.download_sector_data()

def f():
    print(data)
    now = datetime.datetime.now()
    for stock in data:
        if stock not in A.hsa:
            continue
        cuurent_price = data[stock][0]['close']
        pre_price = data[stock][0]['preClose']
        ratio = cuurent_price / pre_price - 1 if pre_price > 0 else 0
        if ratio > 0.09 and stock not in A.bought_list:
            print(f{now} 最新价 买入 {stock})
            async_seq = xt_trader.order_stock_async(acc, stock, xtconstant.STOCK_BUY, 100, xtconstant.LATEST_PRICE, -1,
                                                    'strategy_name', stock)
            A.bought_list.append(stock)

class MyXtQuantTraderCallback():
    def on_disconnected():
        
        连接断开
        :return:

        print(datetime.datetime.now(), '连接断开回调')

    def on_stock_order(, ):
        
        委托回报推送
        :param order: XtOrder对象
        :return:

        print(datetime.datetime.now(), '委托回调', order.order_remark)

    def on_stock_trade(, ):
        
        成交变动推送
        :param trade: XtTrade对象
        :return:

        print(datetime.datetime.now(), '成交回调', trade.order_remark)

    def on_order_error(, ):
        
        委托失败推送
        :param order_error:XtOrderError 对象
        :return:

        
        # print(order_error.order_id, order_error.error_id, order_error.error_msg)
        print(f{order_error.order_remark} {order_error.error_msg})

    def on_cancel_error(, ):
        
        撤单失败推送
        :param cancel_error: XtCancelError 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_order_stock_async_response(, ):
        
        异步下单回报推送
        :param response: XtOrderResponse 对象
        :return:

        print(f{response.order_remark})

    def on_cancel_order_stock_async_response(, ):
        
        :param response: XtCancelOrderResponse 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_account_status(, ):
        
        :param response: XtAccountStatus 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

if __name__ == '__main__':
    print(start)
    # 指定客户端所在路径, 券商端指定到 userdata_mini文件夹
    
    path = r'D:\qmt\投研\迅投极速交易终端睿智融科版\userdata'
    # 生成session id 整数类型 同时运行的策略不能重复
    session_id = (time.time())
    xt_trader = XtQuantTrader(path, session_id)
    # 开启主动请求接口的专用线程 开启后在on_stock_xxx回调函数里调用XtQuantTrader.query_xxx函数不会卡住回调线程，但是查询和推送的数据在时序上会变得不确定
    # 详见: http://docs.thinktrader.net/vip/pages/ee0e9b/#开启主动请求接口的专用线程
    # xt_trader.set_relaxed_response_order_enabled(True)

    # 创建资金账号为 800068 的证券账号对象 股票账号为STOCK 信用CREDIT 期货FUTURE
    acc = StockAccount('2000128', 'STOCK')
    # 创建交易回调类对象，并声明接收回调
    callback = MyXtQuantTraderCallback()
    xt_trader.register_callback(callback)
    # 启动交易线程
    xt_trader.start()
    # 建立交易连接，返回0表示连接成功
    connect_result = xt_trader.connect()
    print('建立交易连接，返回0表示连接成功', connect_result)
    # 对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功
    subscribe_result = xt_trader.subscribe(acc)
    print('对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功', subscribe_result)

    #订阅的品种列表
    code_list = ['600000.SH', '000001.SZ']

    for code in code_list:
        xtdata.subscribe_quote(code, '1d',  = f)

    # 阻塞主线程退出
    xt_trader.run_forever()
    # 如果使用vscode pycharm等本地编辑器 可以进入交互模式 方便调试 （把上一行的run_forever注释掉 否则不会执行到这里）
    interact()

```

```

### 定时判断实盘示例

```python

# coding:utf-8
import time, datetime, traceback, sys
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant

# 定义一个类 创建类的实例 作为状态的容器
class _a():
    pass

A = _a()
A.bought_list = []
A.hsa = xtdata.get_stock_list_in_sector('沪深A股')

def interact():
    
    import code
    code.InteractiveConsole(=globals()).interact()

xtdata.download_sector_data()

def f():
    now = datetime.datetime.now()
    # print(data)
    for stock in data:
        if stock not in A.hsa:
            continue
        cuurent_price = data[stock].iloc[-1, 0]
        pre_price = data[stock].iloc[-2, 0]
        ratio = cuurent_price / pre_price - 1 if pre_price > 0 else 0
        if ratio > 0.09 and stock not in A.bought_list:
            print(f{now} 最新价 买入 {stock})
            async_seq = xt_trader.order_stock_async(acc, stock, xtconstant.STOCK_BUY, 100, xtconstant.LATEST_PRICE, -1,
                                                    'strategy_name', stock)
            A.bought_list.append(stock)

class MyXtQuantTraderCallback():
    def on_disconnected():
        
        连接断开
        :return:

        print(datetime.datetime.now(), '连接断开回调')

    def on_stock_order(, ):
        
        委托回报推送
        :param order: XtOrder对象
        :return:

        print(datetime.datetime.now(), '委托回调', order.order_remark)

    def on_stock_trade(, ):
        
        成交变动推送
        :param trade: XtTrade对象
        :return:

        print(datetime.datetime.now(), '成交回调', trade.order_remark)

    def on_order_error(, ):
        
        委托失败推送
        :param order_error:XtOrderError 对象
        :return:

        
        # print(order_error.order_id, order_error.error_id, order_error.error_msg)
        print(f{order_error.order_remark} {order_error.error_msg})

    def on_cancel_error(, ):
        
        撤单失败推送
        :param cancel_error: XtCancelError 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_order_stock_async_response(, ):
        
        异步下单回报推送
        :param response: XtOrderResponse 对象
        :return:

        print(f{response.order_remark})

    def on_cancel_order_stock_async_response(, ):
        
        :param response: XtCancelOrderResponse 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

    def on_account_status(, ):
        
        :param response: XtAccountStatus 对象
        :return:

        print(datetime.datetime.now(), sys._getframe().f_code.co_name)

if __name__ == '__main__':
    print(start)
    # 指定客户端所在路径, 券商端指定到 userdata_mini文件夹
    
    path = r'D:\qmt\投研\迅投极速交易终端睿智融科版\userdata'
    # 生成session id 整数类型 同时运行的策略不能重复
    session_id = (time.time())
    xt_trader = XtQuantTrader(path, session_id)
    # 开启主动请求接口的专用线程 开启后在on_stock_xxx回调函数里调用XtQuantTrader.query_xxx函数不会卡住回调线程，但是查询和推送的数据在时序上会变得不确定
    # 详见: http://docs.thinktrader.net/vip/pages/ee0e9b/#开启主动请求接口的专用线程
    # xt_trader.set_relaxed_response_order_enabled(True)

    # 创建资金账号为 800068 的证券账号对象 股票账号为STOCK 信用CREDIT 期货FUTURE
    acc = StockAccount('2000128', 'STOCK')
    # 创建交易回调类对象，并声明接收回调
    callback = MyXtQuantTraderCallback()
    xt_trader.register_callback(callback)
    # 启动交易线程
    xt_trader.start()
    # 建立交易连接，返回0表示连接成功
    connect_result = xt_trader.connect()
    print('建立交易连接，返回0表示连接成功', connect_result)
    # 对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功
    subscribe_result = xt_trader.subscribe(acc)
    print('对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功', subscribe_result)

    #订阅的品种列表
    code_list = ['600000.SH', '000001.SZ']
    #遍历品种 下载历史k线 订阅当日行情
    for code in code_list:
        xtdata.download_history_data(code, ='1d', ='20200101')
        xtdata.subscribe_quote(code, '1d',  = None)

    while True:
        now = datetime.datetime.now()
        now_time = now.strftime('%H%M%S')
        if not '093000' <= now_time < '150000':
            print(f{now})
            break
        #取k线数据
        data = xtdata.get_market_data_ex(['close'], code_list, = '1d', = '20240101')
        #判断交易
        f(data)
        #每次循环 睡眠三秒后继续
        time.sleep(3)

    # 阻塞主线程退出
    xt_trader.run_forever()
    # 如果使用vscode pycharm等本地编辑器 可以进入交互模式 方便调试 （把上一行的run_forever注释掉 否则不会执行到这里）
    interact()

```

### 交易接口重连

```

### 指定session id范围连接交易

```

### 信用账号执行还款

```

### 下单后通过回调撤单

```python

import pandas as pd
import numpy as np
import datetime
from xtquant import xtdata,xttrader
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from xtquant.xttrader import XtQuantTraderCallback
import sys
import time

异步下单委托流程为
1.order_stock_async发出委托
2.回调on_order_stock_async_response收到回调信息
3.回调on_stock_order收到委托信息
4.回调cancel_order_stock_sysid_async发出异步撤单指令
5.回调on_cancel_order_stock_async_response收到撤单回调信息
6.回调on_stock_order收到委托信息

strategy_name = 委托撤单测试

class MyXtQuantTraderCallback():
    # 用于接收回调信息的类
    def on_stock_order(, ):
        
        委托回报推送
        :param order: XtOrder对象
        :return:

        # 属性赋值
        account_type = order.account_type  # 账号类型
        account_id = order.account_id  # 资金账号
        stock_code = order.stock_code  
        order_id = order.order_id  # 订单编号
        order_sysid = order.order_sysid  # 柜台合同编号
        order_time = order.order_time  # 报单时间
        order_type = order.order_type  # 委托类型，参见数据字典
        order_volume = order.order_volume  # 委托数量
        price_type = order.price_type  # 报价类型，该字段在返回时为柜台返回类型，不等价于下单传入的price_type，枚举值不一样功能一样，参见数据字典
        price = order.price  # 委托价格
        traded_volume = order.traded_volume  # 成交数量
        traded_price = order.traded_price  # 成交均价
        order_status = order.order_status  # 委托状态，参见数据字典
        status_msg = order.status_msg  # 委托状态描述，如废单原因
        strategy_name = order.strategy_name  # 策略名称
        order_remark = order.order_remark  # 委托备注
        direction = order.direction  # 多空方向，股票不适用；参见数据字典
        offset_flag = order.offset_flag  # 交易操作，用此字段区分股票买卖，期货开、平仓，期权买卖等；参见数据字典

        # 打印输出
        print(f
        =============================
                委托信息
        =============================
        账号类型: {order.account_type}, 
        资金账号: {order.account_id},
        证券代码: {order.stock_code},
        订单编号: {order.order_id}, 
        柜台合同编号: {order.order_sysid},
        报单时间: {order.order_time},
        委托类型: {order.order_type},
        委托数量: {order.order_volume},
        报价类型: {order.price_type},
        委托价格: {order.price},
        成交数量: {order.traded_volume},
        成交均价: {order.traded_price},
        委托状态: {order.order_status},
        委托状态描述: {order.status_msg},
        策略名称: {order.strategy_name},
        委托备注: {order.order_remark},
        多空方向: {order.direction},
        交易操作: {order.offset_flag}
)
        if order.strategy_name == strategy_name:
            # 该委托是由本策略发出
            ssid = order.order_sysid
            status = order.order_status
            market = order.stock_code.split(.)[1]
            # print(ssid)
            if ssid and status in [50,55]:
                ## 使用cancel_order_stock_sysid_async时，投研端market参数可以填写为0，券商端按实际情况填写
                print(xt_trade.cancel_order_stock_sysid_async(account,0,ssid))

    def on_stock_trade(, ):
        
        成交变动推送
        :param trade: XtTrade对象
        :return:

        print(datetime.datetime.now(), '成交回调', trade.order_remark,trade.stock_code,trade.traded_volume,trade.offset_flag)

    def on_order_stock_async_response(, ):
        
        异步下单回报推送
        :param response: XtOrderResponse 对象
        :return:

        
        print(datetime.datetime.now(),'异步下单编号为：',response.seq)

    def on_cancel_order_stock_async_response(, ):
        
        异步撤单回报
        :param response: XtCancelOrderResponse 对象
        :return:

        account_type = response.account_type # 账号类型
        account_id = response.account_id  # 资金账号
        order_id = response.order_id  # 订单编号
        order_sysid = response.order_sysid  # 柜台委托编号
        cancel_result = response.cancel_result  # 撤单结果
        seq = response.seq  # 异步撤单的请求序号

        print(f
            ===========================
                   异步撤单回调信息
            ===========================
            账号类型: {response.account_type}, 
            资金账号: {response.account_id},
            订单编号: {response.order_id}, 
            柜台委托编号: {response.order_sysid},
            撤单结果: {response.cancel_result},
            异步撤单的请求序号: {response.seq})
        pass

callback = MyXtQuantTraderCallback()
# 填投研端的期货账号
account = StockAccount(1000024, = FUTURE)
# 填写投研端的股票账号

# 填投研端的userdata路径,miniqmt指定到userdata_mini
xt_trade = xttrader.XtQuantTrader(rC:\Program Files\测试1\迅投极速交易终端睿智融科版\userdata,(time.time()))
# 注册接受回调
xt_trade.register_callback(callback) 
# 启动交易线程
xt_trade.start()
# 链接交易
connect_result = xt_trade.connect()
# 订阅账号信息，接受这个账号的回调，回调是账号维度的
subscribe_result = xt_trade.subscribe(account)
print(subscribe_result)

code = rb2410.SF

tick = xtdata.get_full_tick([code])[code]

last_price = tick[lastPrice] # 最新价

ask_price = round(tick[askPrice][0],3) # 卖方1档价
bid_price = round(tick[bidPrice][4],3) # 买方5档价

symbol_info = xtdata.get_instrument_detail(code)

up_limit = symbol_info[UpStopPrice]
down_limit = symbol_info[DownStopPrice]

lots = 1
res_id = xt_trade.order_stock_async(account, code, xtconstant.FUTURE_OPEN_LONG, lots, xtconstant.FIX_PRICE, down_limit, strategy_name, 跌停价/固定手数)

# lots = 100

xtdata.run()

```

## 行情示例

## 1.VBA模式获取涨停股

本示例用于获取某列表涨停股。 
示例

```python
stocktype:=INBLOCK('创业板') or INBLOCK('科创板');

lastprice:=ref(c,1);

ZT:IF(stocktype,ROUNDS(lastprice*1.2,2)=close,ROUNDS(lastprice*1.1,2)=close);

```

## 2.如何获取连续放量标的

本示例用于获取连续放量标的。 
示例

```python
B:=VOL>REF(VOL,1);

UPVOL:COUNT(B,M)=M;//持续M个周期放量

```

## 3.MACD背离模型

在相应股票上,建立MACD背离模型，以指标背离作为入场或出出场参考。 
示例

```python
//…………MACD指标计算…………
DIFF:=EMA(CLOSE,12)-EMA(CLOSE,26);
DEA:=EMA(DIFF,9);
MACD:=2*(DIFF-DEA),COLORSTICK;
//……………………………………………………
N:=BARSLAST(CROSS(DIFF,DEA))+1;
N1:=BARSLAST(CROSS(DEA,DIFF))+1;
DIFF1:=REF(REF(DIFF,N-1),1);
DIFF2:=REF(REF(DIFF,N1-1),1);
C1:=REF(REF(C,N-1),1);
C2:=REF(REF(C,N1-1),1);
DBL1:DIFF>DIFF1 AND CROSS(DIFF,DEA) AND C<C1; //底背离
DBL:DIFF<DIFF2 AND  CROSS(DEA,DIFF) AND C>C2; //顶背离

```

## 4.如何在日内分钟级别实现《菲阿里四价》判断
什么是菲阿里四价？
昨天高点、昨天低点、昨日收盘价、今天开盘价，可并称为菲阿里四价。它由日本期货冠军菲阿里实盘采用的主要突破交易参照系统。 
主要特点： 日内交易策略，收盘平仓； 
 上轨＝昨日高点； 
 下轨＝昨日低点；

核心点

实现该指标的核心在于跨周期引用数据，可以使用CALLSTOCK函数。

用法
CALLSTOCK(CODE,TYPE[,CYC,N]),引用指定品种代码为 CODE,周期为 CYC(可选)若不填或者为-1 表示使用当前周期,类型为 TYPE 的数据
N 为左右偏移周期个数（可选）0 表示引用当前数据，<0 为引用之前数据，>0为引用之后数据。
其中 TYPE 的值可为 VTOPEN(开盘) VTHIGH(最高) VTLOW(最低) VTCLOSE(收盘)
VTVOL(成交量) VTAMOUNT(成交额) vtOPENINT(持仓量) VTADVANCE(涨数,大盘有效) VTDECLINE(跌数,大盘有效)以及外部数据和万德数据
如果找不到同期数据，那么将返回最近的一个。
CYC 范围为 0-19，分别表示
0:分笔成交、1:1 分钟、2:5 分钟、3:15 分钟、4:30 分钟、5:60 分钟
6:日、7:周、8:月、9:年、10:多日、11:多分钟、12:多秒
13:多小时、14:季度线、15:半年线、16:节气线、17:3 分钟、18:10 分钟、19:多笔线

 `注意`引用数据时，需要确认被引用品种周期数据齐全，在首次使用或者在不确定时，请手工进行数据下载工作；

示例

```python
昨高:=callstock('',vthigh,6,-1);//获取当前主图标的昨高
昨低:=callstock('',vtlow,6,-1);//获取当前主图标的昨低
昨收:=callstock('',vtclose,6,-1);//获取当前主图标的昨收
上轨:昨高;
下轨:昨低;

```

## 回测示例

### 单股回测模型A

参见默认脚本`单股回测模型A`

### 单股回测模型B

参见默认脚本`单股回测模型B`