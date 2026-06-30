# coding: utf-8
"""
framework/stock_filter.py
股票过滤器体系 —— StockFilter（基类）、StaticStockFilter（静态列表实现）。

设计原则：
  - 股票池不再是一个预加载的代码列表，而是一个过滤器
  - 每个时间点触发时，由过滤器动态返回当前关注的标的列表
- 纯 Python 类
"""
from typing import List


class StockFilter:
    """股票过滤器基类。

    子类需实现 get_stocks(timestamp) 方法，返回当前时间点应关注的标的列表。

    用法示例（自定义动态选股）::

        class MyFilter(StockFilter):
            def get_stocks(self, timestamp) -> List[str]:
                # 根据时间点动态返回标的
                return ['000001.SZ', '600000.SH']
    """

    def get_stocks(self, timestamp) -> List[str]:
        """获取当前时间点应关注的标的列表。

        Args:
            timestamp: 当前时间点的时间戳（秒级或毫秒级整数）

        Returns:
            List[str]: 股票代码列表，如 ['000001.SZ', '600000.SH']
        """
        return []


class StaticStockFilter(StockFilter):
    """静态股票过滤器。

    从配置文件的 stock_list 字段读取固定列表，每次调用直接返回该列表。
    用于兼容现有策略配置，无需策略开发者修改任何代码。

    用法示例::

        filter_ = StaticStockFilter(['000001.SZ', '600000.SH'])
        stocks = filter_.get_stocks(timestamp)  # 始终返回 ['000001.SZ', '600000.SH']
    """

    def __init__(self, stock_list: List[str]):
        """初始化静态股票过滤器。

        Args:
            stock_list: 固定的股票代码列表
        """
        self._stock_list = list(stock_list) if stock_list else []

    def get_stocks(self, timestamp) -> List[str]:
        """返回固定的股票代码列表（忽略 timestamp 参数）。

        Args:
            timestamp: 当前时间点（本实现中忽略此参数）

        Returns:
            List[str]: 固定的股票代码列表
        """
        return self._stock_list
