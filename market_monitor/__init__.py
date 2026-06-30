"""
market_monitor — 市场行情监控分析模块

提供每日收盘后的市场行情监控分析功能：
  1. 市场全景扫描：大盘指数 + 全市场涨跌分布 + 量能分析 + 新高新低统计
  2. 个股异动/涨停板监控：涨停、跌停、连板、炸板、量价异动
  3. 行业板块轮动分析：申万一级行业涨跌排名 + 近期轮动强度

数据来源：本地 Parquet 缓存（stock/kline、index/kline、stock/instrument、industry/members）
输出形式：HTML 报告（market_report_{YYYYMMDD}.html）

使用方式：
    from market_monitor import MarketMonitorService
    from data_manager.data_service import ServiceCallbacks

    service = MarketMonitorService()
    result = service.run(
        params={'type': 'all', 'date': '20260522', 'sector': '沪深A股'},
        callbacks=ServiceCallbacks(),
    )
    print(result['output_path'])
"""

from .market_service import MarketMonitorService

__all__ = [
    "MarketMonitorService",
]

__version__ = "1.0.0"
