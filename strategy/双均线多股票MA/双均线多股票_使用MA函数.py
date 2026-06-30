# coding: utf-8  # 源文件编码
# 策略说明：
# - 策略名称：双均线多股票（使用 MyTT.MA）
# - 功能：对股票池内每只股票，比较当日 MA5 与 MA20；MA5>MA20 买入，MA5<MA20 卖出
# - 指标来源：使用 MyTT 库的 MA 函数（对收盘价序列计算均线）
# - 与使用 MyTT.MA 的版本区别：moving_avg 中内置了行情获取 + 移动平均，更加方便，MyTT.MA 需要在策略文档中先拉取历史行情再计算
from utils.quant_import import *  # 统一导入工具与指标

def init(stocks=None, data=None):  # 策略初始化（无需特殊处理）
    """本策略不需初始化"""
    pass  # 占位


def on_bar(data: Dict) -> List[Dict]:  # 主策略函数
    """多股票双均线（MyTT.MA）策略：MA5 上穿 MA20 买入，反向卖出"""
    signals = []  # 信号列表
    stock_list = get_data(data, "stocks")  # 股票池
    dn = get_data(data, "date_num")  # 当前日期(数值格式)

    for sc in stock_list:  # 遍历股票
        hist = get_history(sc, ["close"], 60, "1d", dn, fq="pre", force_download=False)  # 拉取60日收盘价
        closes = hist[sc]["close"].values  # 收盘序列
        ma5_now = float(MA(closes, 5)[-1])  # 当日MA5
        ma20_now = float(MA(closes, 20)[-1])  # 当日MA20

        price = get_price(data, sc, "open")  # 当日开盘价
        has_pos = has_position(data, sc)  # 是否持仓

        if ma5_now > ma20_now and not has_pos:  # 金叉且无持仓→买入
            signals.extend(generate_signal(data, sc, price, 0.5, "buy", f"{sc[:6]} 金叉买入"))  # 0.5仓
        elif ma5_now < ma20_now and has_pos:  # 死叉且有持仓→卖出
            signals.extend(generate_signal(data, sc, price, 1.0, "sell", f"{sc[:6]} 死叉卖出"))  # 全部卖出

    return signals  # 返回信号

