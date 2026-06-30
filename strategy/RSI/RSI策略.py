# coding: utf-8
# 策略说明：
# - 策略名称：RSI 策略
# - 功能：多只股票，比较当日 RSI(14) 与 30/70；RSI<30 买入，RSI>70 卖出
# - 指标来源：使用 MyTT 库的 RSI 函数（对收盘价序列计算RSI）
from utils.quant_import import *  # 导入统一工具与指标

def init(stocks=None, data=None):  # 初始化（无需特殊处理）
    """策略初始化（本策略无需特殊初始化）"""
    pass  # 占位

def on_bar(data: Dict) -> List[Dict]:  # 主策略函数
    signals = []  # 信号列表
    dn = get_data(data, "date_num")  # 当前日期(数值格式)
    for sc in get_data(data, "stocks"):  # 遍历股票池
        hist = get_history(sc, ["close"], 60, "1d", dn, fq="pre", force_download=False)  # 拉取60日收盘价
        r = RSI(hist[sc]["close"].values, 14)  # 计算RSI(14)
        rp, rn = float(r[-2]), float(r[-1])  # 前一日与当日RSI
        p = get_price(data, sc, "open")  # 当日开盘价
        if (rp < 30 <= rn) and not has_position(data, sc):  # RSI上穿30且无持仓→买入
            signals.extend(generate_signal(data, sc, p, 0.5, "buy", f"{sc[:6]} RSI 上穿30，{rn:.2f}"))  # 0.5仓
        elif (rp > 70 >= rn) and has_position(data, sc):  # RSI下穿70且有持仓→卖出
            signals.extend(generate_signal(data, sc, p, 1.0, "sell", f"{sc[:6]} RSI 下穿70，{rn:.2f}"))  # 全部卖出
    return signals  # 返回信号

