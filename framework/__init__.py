# coding: utf-8
"""
framework/ — 量化交易核心框架包

公共接口导出：
  - QuantFramework      主框架类
- MyTraderCallback    交易回调类（实盘使用）
  - FrameworkCallbacks  回调协议（Protocol）
  - DefaultCallbacks    默认回调实现
  - TriggerBase / TickTrigger / KLineTrigger / CustomTimeTrigger / TriggerFactory
  - get_version / get_version_info / get_channel / VERSION_INFO
"""

from framework.core import QuantFramework, MyTraderCallback          # noqa: F401
from framework.callbacks import FrameworkCallbacks, DefaultCallbacks  # noqa: F401
from framework.stock_filter import StockFilter, StaticStockFilter     # noqa: F401
from framework.triggers import (                                       # noqa: F401
    TriggerBase,
    TickTrigger,
    KLineTrigger,
    CustomTimeTrigger,
    TriggerFactory,
)
from framework.version import (                                        # noqa: F401
    VERSION_INFO,
    get_version,
    get_version_info,
    get_channel,
)

__all__ = [
    "QuantFramework",
    "MyTraderCallback",
    "FrameworkCallbacks",
    "DefaultCallbacks",
    "StockFilter",
    "StaticStockFilter",
    "TriggerBase",
    "TickTrigger",
    "KLineTrigger",
    "CustomTimeTrigger",
    "TriggerFactory",
    "VERSION_INFO",
    "get_version",
    "get_version_info",
    "get_channel",
]
