# coding: utf-8
"""
framework/backtest/mixin.py
BacktestMixin 主类 —— 通过 import 组合 runner / recorder / performance 子模块的方法。
由 QuantFramework 通过多继承引入，不可单独实例化。
"""
from framework.backtest.runner import _run_backtest
from framework.backtest.recorder import record_results, _record_daily_stats
from framework.backtest.performance import _calc_summary_metrics
from framework.backtest.saver import _save_backtest_results


class BacktestMixin:
    """回测逻辑 Mixin"""

    # 绑定来自各子模块的方法
    _run_backtest = _run_backtest
    record_results = record_results
    _record_daily_stats = _record_daily_stats
    _calc_summary_metrics = _calc_summary_metrics
    _save_backtest_results = _save_backtest_results
