# -*- coding: utf-8 -*-
"""
utils — 项目公共工具模块

提供策略与核心层共享的纯逻辑工具函数（股票工具、策略工具等），
不依赖外部 UI 框架，可在 CLI / 测试场景中直接使用。
"""

from utils.stock_utils import (
    is_etf,
    determine_pool_type,
    load_t0_etf_list,
    is_t0_etf,
    check_t0_support,
    get_t0_details,
    get_price_decimals,
    round_price,
    format_price,
    is_trade_time,
    is_trade_day,
    get_trade_days_count,
    QuTools,
)
from utils.strategy_utils import (
    moving_avg,
    calculate_max_buy_volume,
    generate_signal,
    StopLossManager,
    BarFrequencyAdapter,
)

__all__ = [
    # stock_utils
    "is_etf",
    "determine_pool_type",
    "load_t0_etf_list",
    "is_t0_etf",
    "check_t0_support",
    "get_t0_details",
    "get_price_decimals",
    "round_price",
    "format_price",
    "is_trade_time",
    "is_trade_day",
    "get_trade_days_count",
    "QuTools",
    # strategy_utils
    "moving_avg",
    "calculate_max_buy_volume",
    "generate_signal",
    "StopLossManager",
    "BarFrequencyAdapter",
]
