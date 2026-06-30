# -*- coding: utf-8 -*-
"""
utils/stock_utils.py — 股票类型判断、T+0、价格工具、交易时间工具函数

从 utils/stock_utils.py 迁移而来。
可在 CLI、服务器、单元测试中直接使用。
"""

import csv
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import holidays

# ============================================================================
# 全局变量
# ============================================================================

_trading_periods = [
    ("093000", "113000"),  # 上午
    ("130000", "150000"),  # 下午
]
_cn_holidays = holidays.China()

# 默认价格精度（股票为2位，ETF为3位）
_default_price_decimals = 2

# 全局缓存T0 ETF列表，避免重复读取文件
_t0_etf_cache = None


# ============================================================================
# 股票类型判断
# ============================================================================

def is_etf(stock_code: str) -> bool:
    """判断是否为ETF（不包括LOF）

    Args:
        stock_code: 股票代码，如 "510300.SH" 或 "159915.SZ"

    Returns:
        bool: 是否为ETF

    说明:
        上海ETF: 51(主流)、52(跨境)、53(部分)、55(债券)、56(新规)、58(科创)
        深圳ETF: 159开头（深交所ETF统一为159开头）
        注意：50/16开头是LOF，不是ETF
    """
    code = stock_code.split('.')[0]
    sh_etf_prefixes = ('51', '52', '53', '55', '56', '58')
    sz_etf_prefix = '159'
    return code.startswith(sh_etf_prefixes) or code.startswith(sz_etf_prefix)


def determine_pool_type(stock_list: List[str]) -> tuple:
    """判断股票池类型，返回类型和对应的价格精度

    Args:
        stock_list: 股票代码列表

    Returns:
        tuple: (pool_type, price_decimals)
            pool_type: 'stock_only' | 'etf_only' | 'mixed'
            price_decimals: 2（纯股票）或 3（含ETF或混合）
    """
    if not stock_list:
        return ('stock_only', 2)

    has_stock = any(not is_etf(code) for code in stock_list)
    has_etf = any(is_etf(code) for code in stock_list)

    if has_stock and not has_etf:
        return ('stock_only', 2)
    elif has_etf and not has_stock:
        return ('etf_only', 3)
    else:
        return ('mixed', 3)


# ============================================================================
# T+0 交易模式相关函数
# ============================================================================

def load_t0_etf_list() -> set:
    """加载T0型ETF列表

    Returns:
        set: T0型ETF的股票代码集合
    """
    global _t0_etf_cache

    if _t0_etf_cache is not None:
        return _t0_etf_cache

    _t0_etf_cache = set()

    # 数据文件路径：utils/data/T0型ETF.csv
    current_dir = os.path.dirname(os.path.abspath(__file__))
    t0_file = os.path.join(current_dir, 'data', 'T0型ETF.csv')

    if not os.path.exists(t0_file):
        logging.warning(f"T0型ETF列表文件不存在: {t0_file}")
        return _t0_etf_cache

    try:
        with open(t0_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and len(row) >= 1:
                    stock_code = row[0].strip()
                    if stock_code:
                        _t0_etf_cache.add(stock_code)
        logging.info(f"已加载 {len(_t0_etf_cache)} 只T0型ETF")
    except Exception as e:
        logging.error(f"加载T0型ETF列表失败: {e}")

    return _t0_etf_cache


def is_t0_etf(stock_code: str) -> bool:
    """判断单个股票是否支持T+0交易

    Args:
        stock_code: 股票代码，如 '159001.SZ'

    Returns:
        bool: 是否支持T+0
    """
    t0_list = load_t0_etf_list()
    return stock_code in t0_list


def check_t0_support(stock_list: List[str]) -> tuple:
    """检验股票池的T+0支持情况

    Args:
        stock_list: 股票代码列表

    Returns:
        tuple: (support_type, is_t0_mode)
            support_type: 'all_t0' | 'mixed' | 'no_t0'
            is_t0_mode: True（全T+0）/ False（其他情况）
    """
    if not stock_list:
        return ('no_t0', False)

    t0_list = load_t0_etf_list()
    t0_count = sum(1 for code in stock_list if code in t0_list)
    total_count = len(stock_list)

    if t0_count == total_count:
        return ('all_t0', True)
    elif t0_count > 0:
        return ('mixed', False)
    else:
        return ('no_t0', False)


def get_t0_details(stock_list: List[str]) -> dict:
    """获取股票池中T+0支持的详细信息

    Args:
        stock_list: 股票代码列表

    Returns:
        dict: {
            't0_stocks': List[str],
            'non_t0_stocks': List[str],
            't0_count': int,
            'total_count': int
        }
    """
    t0_list = load_t0_etf_list()
    t0_stocks = [code for code in stock_list if code in t0_list]
    non_t0_stocks = [code for code in stock_list if code not in t0_list]

    return {
        't0_stocks': t0_stocks,
        'non_t0_stocks': non_t0_stocks,
        't0_count': len(t0_stocks),
        'total_count': len(stock_list),
    }


# ============================================================================
# 价格精度相关函数
# ============================================================================

def get_price_decimals(data: Dict = None) -> int:
    """从数据字典中获取价格精度设置

    Args:
        data: 策略接收的数据对象，包含框架信息 __framework__

    Returns:
        int: 价格精度（小数位数），默认为2
    """
    if data is None:
        return _default_price_decimals

    framework = data.get("__framework__", None)
    if framework and hasattr(framework, 'price_decimals'):
        return framework.price_decimals

    return _default_price_decimals


def round_price(price: float, decimals: int = None, data: Dict = None) -> float:
    """根据精度设置对价格进行四舍五入

    Args:
        price: 原始价格
        decimals: 精度（小数位数），如果为None则从data中获取
        data: 策略接收的数据对象

    Returns:
        float: 四舍五入后的价格
    """
    if decimals is None:
        decimals = get_price_decimals(data)
    return round(price, decimals)


def format_price(price: float, decimals: int = None, data: Dict = None) -> str:
    """根据精度设置格式化价格为字符串

    Args:
        price: 价格
        decimals: 精度（小数位数），如果为None则从data中获取
        data: 策略接收的数据对象

    Returns:
        str: 格式化后的价格字符串
    """
    if decimals is None:
        decimals = get_price_decimals(data)
    return f"{price:.{decimals}f}"


# ============================================================================
# 交易时间判断
# ============================================================================

def is_trade_time() -> bool:
    """判断是否为交易时间"""
    current = time.strftime("%H%M%S")
    for start, end in _trading_periods:
        if start <= current <= end:
            return True
    return False


def is_trade_day(date_str: str = None) -> bool:
    """判断是否为交易日（工作日且非法定节假日）

    Args:
        date_str: 日期字符串，支持格式：
                 - "YYYY-MM-DD" (如: "2024-12-25")
                 - "YYYYMMDD" (如: "20241225")
                 - None (默认为当天)

    Returns:
        bool: 是否为交易日
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    try:
        date_obj = None

        if '-' in date_str and len(date_str) == 10:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        elif date_str.isdigit() and len(date_str) == 8:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
        else:
            for fmt in ["%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"]:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        if date_obj is None:
            raise ValueError(f"无法解析日期格式: {date_str}")

        if date_obj.weekday() >= 5:
            return False

        date_only = date_obj.date()
        if date_only in _cn_holidays:
            return False

        return True

    except Exception as e:
        print(f"判断交易日异常: {str(e)}")
        try:
            date_obj = None
            for fmt in ["%Y-%m-%d", "%Y%m%d"]:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if date_obj is None:
                print(f"无法解析日期格式: {date_str}，默认按交易日处理")
                return True

            date_only = date_obj.date()
            if date_only in _cn_holidays:
                return False
            if date_obj.weekday() >= 5:
                return False
            return True
        except Exception:
            print(f"无法确定 {date_str} 是否为交易日，默认按普通工作日处理")
            return True


def get_trade_days_count(start_date: str, end_date: str) -> int:
    """计算指定日期范围内的交易日天数

    Args:
        start_date: 起始日期，格式为"YYYY-MM-DD"
        end_date: 结束日期，格式为"YYYY-MM-DD"

    Returns:
        int: 交易日天数
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        if start_dt > end_dt:
            logging.error(f"起始日期 {start_date} 晚于结束日期 {end_date}")
            return 0

        trade_days = 0
        current_dt = start_dt
        while current_dt <= end_dt:
            if is_trade_day(current_dt.strftime("%Y-%m-%d")):
                trade_days += 1
            current_dt += timedelta(days=1)

        logging.info(f"从 {start_date} 到 {end_date} 共有 {trade_days} 个交易日")
        return trade_days

    except Exception as e:
        logging.error(f"计算交易日天数时出错: {str(e)}")
        return 0


# ============================================================================
# 兼容性：保留原有的 QuTools 类
# ============================================================================

class QuTools:
    """量化工具类（兼容性保留，推荐直接使用模块级函数）"""

    def __init__(self):
        self.trading_periods = _trading_periods
        self.cn_holidays = _cn_holidays

    def is_trade_time(self) -> bool:
        return is_trade_time()

    def is_trade_day(self, date_str: str = None) -> bool:
        return is_trade_day(date_str)

    def get_trade_days_count(self, start_date: str, end_date: str) -> int:
        return get_trade_days_count(start_date, end_date)
