# coding: utf-8
"""
framework/backtest.py
入口转发文件 —— 保持向后兼容的 import 路径。
实际实现已移至 framework/backtest/ 目录：
  - runner.py      : _run_backtest 主流程
  - recorder.py    : record_results、_record_daily_stats
  - performance.py : _calc_summary_metrics
  - mixin.py       : BacktestMixin 主类
"""
from framework.backtest.mixin import BacktestMixin  # noqa: F401

__all__ = ["BacktestMixin"]
