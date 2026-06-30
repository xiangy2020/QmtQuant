# coding: utf-8
"""
framework/backtest/performance.py
回测绩效指标计算 —— _calc_summary_metrics。
由 BacktestMixin 通过 mixin.py 引入，不可单独实例化。
"""
import logging

import numpy as np
import pandas as pd


def _calc_summary_metrics(
    self,
    daily_stats_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    annual_return: float,
    risk_free_rate: float = 0.03,
) -> dict:
    """计算并返回全量评估指标字典。

    Args:
        daily_stats_df: 每日统计 DataFrame，含 daily_return 列
        trades_df:       交易记录 DataFrame，含 action/price/volume/code 列
        benchmark_df:    基准数据 DataFrame，含 close 列；可为 None
        annual_return:   已计算好的年化收益率（小数形式，如 0.045）
        risk_free_rate:  无风险利率（小数形式，默认 0.03）

    Returns:
        dict: 包含 sharpe_ratio / sortino_ratio / volatility /
              alpha / beta / win_rate / profit_loss_ratio / risk_free_rate
    """
    result = {
        'sharpe_ratio': None,
        'sortino_ratio': None,
        'volatility': None,
        'alpha': None,
        'beta': None,
        'win_rate': None,
        'profit_loss_ratio': None,
        'risk_free_rate': risk_free_rate,
    }

    # ── 日收益率序列 ──────────────────────────────────────────
    if 'daily_return' not in daily_stats_df.columns:
        return result

    returns = pd.to_numeric(daily_stats_df['daily_return'], errors='coerce').dropna()
    n = len(returns)
    if n < 2:
        return result

    # ── 年化波动率 ────────────────────────────────────────────
    try:
        r_mean = returns.mean()
        volatility = float(np.sqrt((250 / n) * np.sum((returns - r_mean) ** 2)))
        if np.isnan(volatility) or np.isinf(volatility):
            volatility = None
        result['volatility'] = volatility
    except Exception as e:
        logging.warning(f"计算年化波动率时出错: {e}")

    # ── 夏普比率 ──────────────────────────────────────────────
    try:
        vol = result['volatility']
        if vol and vol > 0:
            # annual_return 已是小数形式（如 0.045 表示 4.5%）
            annual_ret_decimal = annual_return / 100.0  # summary 中存的是百分比形式
            sharpe = (annual_ret_decimal - risk_free_rate) / vol
            if np.isnan(sharpe) or np.isinf(sharpe):
                sharpe = None
            result['sharpe_ratio'] = sharpe
    except Exception as e:
        logging.warning(f"计算夏普比率时出错: {e}")

    # ── 索提诺比率 ────────────────────────────────────────────
    try:
        # 下行波动率：只计算收益率为负的部分
        downside_returns = returns[returns < 0]
        if len(downside_returns) >= 2:
            downside_risk = float(np.sqrt((250 / n) * np.sum(downside_returns ** 2)))
            if downside_risk > 0 and not np.isnan(downside_risk):
                annual_ret_decimal = annual_return / 100.0
                sortino = (annual_ret_decimal - risk_free_rate) / downside_risk
                if np.isnan(sortino) or np.isinf(sortino):
                    sortino = None
                result['sortino_ratio'] = sortino
    except Exception as e:
        logging.warning(f"计算索提诺比率时出错: {e}")

    # ── Alpha / Beta（需要基准数据）───────────────────────────
    try:
        if benchmark_df is not None and len(benchmark_df) >= 10 and 'close' in benchmark_df.columns:
            bm_prices = pd.to_numeric(benchmark_df['close'], errors='coerce').dropna()
            if len(bm_prices) >= 2:
                bm_returns = bm_prices.pct_change().dropna()

                # 对齐长度（取较短的）
                min_len = min(len(returns), len(bm_returns))
                if min_len >= 10:
                    strat_r = returns.iloc[-min_len:].values
                    bench_r = bm_returns.iloc[-min_len:].values

                    # Beta = Cov(策略, 基准) / Var(基准)
                    cov_matrix = np.cov(strat_r, bench_r)
                    bench_var = np.var(bench_r)
                    if bench_var > 0:
                        beta = float(cov_matrix[0, 1] / bench_var)
                        if np.isnan(beta) or np.isinf(beta):
                            beta = None
                        result['beta'] = beta

                        # Alpha = Ra - [Rf + β * (Rb - Rf)]
                        # 基准年化收益率
                        bm_total_ret = float((1 + bm_returns).prod() - 1)
                        bm_annual_ret = float(pow(1 + bm_total_ret, 250 / len(bm_returns)) - 1)
                        annual_ret_decimal = annual_return / 100.0
                        alpha = annual_ret_decimal - (risk_free_rate + beta * (bm_annual_ret - risk_free_rate))
                        if np.isnan(alpha) or np.isinf(alpha):
                            alpha = None
                        result['alpha'] = alpha
    except Exception as e:
        logging.warning(f"计算 Alpha/Beta 时出错: {e}")

    # ── 胜率 / 盈亏比（基于交易记录）─────────────────────────
    try:
        if trades_df is not None and len(trades_df) > 0:
            total_trades = 0
            winning_trades = 0
            total_profit = 0.0
            total_loss = 0.0

            for code in trades_df['code'].unique():
                code_trades = trades_df[trades_df['code'] == code].sort_values('datetime')
                position = 0
                cost_basis = 0.0

                for _, trade in code_trades.iterrows():
                    action = str(trade.get('action', '')).lower()
                    price = float(trade.get('price', 0))
                    volume = float(trade.get('volume', 0))

                    if action == 'buy':
                        new_pos = position + volume
                        if new_pos > 0:
                            cost_basis = (cost_basis * position + price * volume) / new_pos
                        position = new_pos
                    elif action == 'sell' and position > 0:
                        sell_vol = min(position, volume)
                        pnl = (price - cost_basis) * sell_vol
                        total_trades += 1
                        if pnl > 0:
                            winning_trades += 1
                            total_profit += pnl
                        else:
                            total_loss += abs(pnl)
                        position -= sell_vol

            if total_trades > 0:
                result['win_rate'] = float(winning_trades / total_trades * 100)
                result['profit_loss_ratio'] = float(total_profit / total_loss) if total_loss > 0 else None
    except Exception as e:
        logging.warning(f"计算胜率/盈亏比时出错: {e}")

    return result
