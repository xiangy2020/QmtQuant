"""
market_overview.py — 市场全景扫描

每日收盘后的市场整体温度分析，包含：
  1. 大盘指数行情（上证指数、沪深300 等，数据缺失时显示"数据缺失"）
  2. 全市场涨跌分布（上涨/下跌/平盘/涨停/跌停家数）
  3. 全市场量能分析（总成交额 + 近5日/20日均值对比）
  4. 新高新低统计（20/60/250 日新高、新低股票数量）

数据来源：
  - index/kline/1d：指数 K 线
  - stock/kline/1d：股票 K 线
  - stock/instrument：合约信息（涨跌停价）
  - industry/members/沪深A股.parquet：全市场股票池

设计原则：
  - 大盘指数严格使用 index/kline 数据，数据缺失显示"数据缺失"，不用其他数据替代
  - 涨跌停判断严格使用 up_stop_price / down_stop_price，不用固定比例估算
  - 过滤停牌股和幽灵标的后再做统计
"""

import logging
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from .data_loader import DataLoader

logger = logging.getLogger(__name__)

# 监控的指数列表（代码 → 显示名称）
WATCH_INDICES = {
    '000001.SH': '上证指数',
    '000300.SH': '沪深300',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000688.SH': '科创50',
    '000016.SH': '上证50',
}


class MarketOverview:
    """
    市场全景扫描分析器。

    analyze() 返回结构：
    {
        'trade_date':    str,           # 分析日期 YYYYMMDD
        'indices':       list[dict],    # 大盘指数行情列表
        'breadth':       dict,          # 涨跌分布统计
        'turnover':      dict,          # 量能分析
        'high_low':      dict,          # 新高新低统计
    }
    """

    def __init__(self, loader: DataLoader):
        self._loader = loader

    def analyze(self, trade_date: str, sector: str = '沪深A股') -> Dict[str, Any]:
        """
        执行市场全景扫描。

        Args:
            trade_date: 分析日期 YYYYMMDD
            sector:     股票池板块名称（默认 '沪深A股'）

        Returns:
            全景扫描结果字典
        """
        logger.info(f"[MarketOverview] 开始全景扫描，日期={trade_date}，板块={sector}")

        # ── 1. 大盘指数行情 ───────────────────────────────────────
        indices_data = self._analyze_indices(trade_date)

        # ── 2. 加载全市场股票池 ───────────────────────────────────
        all_symbols = self._loader.load_sector_members(sector)
        if not all_symbols:
            logger.warning(f"[MarketOverview] 板块 {sector} 无成分股数据")

        # ── 3. 加载当日 K 线（需要足够历史数据用于新高新低计算）──
        # 250 日新高需要约 350 个自然日的历史数据
        start_date = self._loader.get_n_days_before(trade_date, 400)
        self._loader._log(f"[MarketOverview] 加载股票 K 线，起始={start_date}，共 {len(all_symbols)} 只...")

        kline_data = self._loader.load_stock_kline_batch(
            all_symbols, '1d', start_date=start_date, end_date=trade_date
        )

        # ── 4. 过滤停牌股和幽灵标的 ──────────────────────────────
        valid_symbols = self._loader.filter_valid_symbols(
            all_symbols, trade_date, kline_data
        )

        # ── 5. 加载合约信息（涨跌停价）───────────────────────────
        instrument_df = self._loader.load_instrument_detail()

        # ── 6. 涨跌分布统计 ──────────────────────────────────────
        breadth = self._analyze_breadth(valid_symbols, trade_date, kline_data, instrument_df)

        # ── 7. 量能分析 ───────────────────────────────────────────
        turnover = self._analyze_turnover(valid_symbols, trade_date, kline_data)

        # ── 8. 新高新低统计 ───────────────────────────────────────
        high_low = self._analyze_high_low(valid_symbols, trade_date, kline_data)

        return {
            'trade_date': trade_date,
            'indices':    indices_data,
            'breadth':    breadth,
            'turnover':   turnover,
            'high_low':   high_low,
        }

    # ──────────────────────────────────────────────────────────────
    # 大盘指数行情
    # ──────────────────────────────────────────────────────────────

    def _analyze_indices(self, trade_date: str) -> List[Dict]:
        """
        读取各大盘指数当日行情。
        数据缺失时在对应字段填入 None（报告层显示"数据缺失"）。
        """
        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')
        result = []

        for symbol, name in WATCH_INDICES.items():
            entry = {
                'symbol':   symbol,
                'name':     name,
                'open':     None,
                'high':     None,
                'low':      None,
                'close':    None,
                'pre_close': None,
                'pct_chg':  None,
                'volume':   None,
                'amount':   None,
                'missing':  True,   # True 表示数据缺失
            }

            df = self._loader.load_index_kline(symbol, '1d',
                                               start_date=trade_date,
                                               end_date=trade_date)
            if df.empty:
                result.append(entry)
                continue

            # 取当日数据
            day_data = df[df.index.normalize() == target_dt]
            if day_data.empty:
                result.append(entry)
                continue

            row = day_data.iloc[0]
            close     = _safe_float(row.get('close'))
            pre_close = _safe_float(row.get('preClose'))

            if close is None:
                result.append(entry)
                continue

            pct_chg = None
            if pre_close and pre_close != 0:
                pct_chg = round((close - pre_close) / pre_close * 100, 2)

            entry.update({
                'open':      _safe_float(row.get('open')),
                'high':      _safe_float(row.get('high')),
                'low':       _safe_float(row.get('low')),
                'close':     close,
                'pre_close': pre_close,
                'pct_chg':   pct_chg,
                'volume':    _safe_float(row.get('volume')),
                'amount':    _safe_float(row.get('amount')),
                'missing':   False,
            })
            result.append(entry)

        return result

    # ──────────────────────────────────────────────────────────────
    # 涨跌分布统计
    # ──────────────────────────────────────────────────────────────

    def _analyze_breadth(
        self,
        symbols: List[str],
        trade_date: str,
        kline_data: Dict[str, pd.DataFrame],
        instrument_df: pd.DataFrame,
    ) -> Dict:
        """
        统计全市场涨跌分布：上涨/下跌/平盘/涨停/跌停家数。
        涨跌停判断严格使用 up_stop_price / down_stop_price。
        """
        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')

        up_count     = 0  # 上涨
        down_count   = 0  # 下跌
        flat_count   = 0  # 平盘
        limit_up     = 0  # 涨停
        limit_down   = 0  # 跌停
        no_data      = 0  # 无当日数据

        for symbol in symbols:
            df = kline_data.get(symbol)
            if df is None or df.empty:
                no_data += 1
                continue

            day_data = df[df.index.normalize() == target_dt]
            if day_data.empty:
                no_data += 1
                continue

            row = day_data.iloc[0]
            close     = _safe_float(row.get('close'))
            pre_close = _safe_float(row.get('preClose'))

            if close is None or pre_close is None or pre_close == 0:
                no_data += 1
                continue

            # 涨跌方向
            if close > pre_close:
                up_count += 1
            elif close < pre_close:
                down_count += 1
            else:
                flat_count += 1

            # 涨跌停判断（严格使用合约信息中的涨跌停价）
            if not instrument_df.empty and symbol in instrument_df.index:
                inst = instrument_df.loc[symbol]
                up_stop   = _safe_float(inst.get('up_stop_price'))
                down_stop = _safe_float(inst.get('down_stop_price'))

                if up_stop is not None and close >= up_stop:
                    limit_up += 1
                if down_stop is not None and close <= down_stop:
                    limit_down += 1

        total = up_count + down_count + flat_count
        return {
            'total':      total,
            'up':         up_count,
            'down':       down_count,
            'flat':       flat_count,
            'limit_up':   limit_up,
            'limit_down': limit_down,
            'no_data':    no_data,
        }

    # ──────────────────────────────────────────────────────────────
    # 量能分析
    # ──────────────────────────────────────────────────────────────

    def _analyze_turnover(
        self,
        symbols: List[str],
        trade_date: str,
        kline_data: Dict[str, pd.DataFrame],
    ) -> Dict:
        """
        计算全市场总成交额及与近5日/20日均值对比。
        """
        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')

        # 收集每只股票的历史成交额序列（按日期）
        daily_amounts: Dict[pd.Timestamp, float] = {}

        for symbol in symbols:
            df = kline_data.get(symbol)
            if df is None or df.empty or 'amount' not in df.columns:
                continue

            # 按日期汇总（normalize 去掉时分秒）
            for dt, row in df.iterrows():
                amt = _safe_float(row.get('amount'))
                if amt is None or amt <= 0:
                    continue
                day = dt.normalize()
                daily_amounts[day] = daily_amounts.get(day, 0.0) + amt

        if not daily_amounts:
            return {
                'today':        None,
                'avg_5d':       None,
                'avg_20d':      None,
                'ratio_5d':     None,
                'ratio_20d':    None,
            }

        # 按日期排序
        sorted_days = sorted(daily_amounts.keys())
        amounts_series = pd.Series(
            [daily_amounts[d] for d in sorted_days],
            index=sorted_days,
        )

        # 当日成交额
        today_amount = daily_amounts.get(target_dt)

        # 近5日/20日均值（不含当日）
        before_today = amounts_series[amounts_series.index < target_dt]
        avg_5d  = float(before_today.tail(5).mean())  if len(before_today) >= 1 else None
        avg_20d = float(before_today.tail(20).mean()) if len(before_today) >= 1 else None

        ratio_5d  = round(today_amount / avg_5d,  2) if today_amount and avg_5d  else None
        ratio_20d = round(today_amount / avg_20d, 2) if today_amount and avg_20d else None

        return {
            'today':     round(today_amount / 1e8, 2) if today_amount else None,   # 亿元
            'avg_5d':    round(avg_5d  / 1e8, 2) if avg_5d  else None,
            'avg_20d':   round(avg_20d / 1e8, 2) if avg_20d else None,
            'ratio_5d':  ratio_5d,
            'ratio_20d': ratio_20d,
        }

    # ──────────────────────────────────────────────────────────────
    # 新高新低统计
    # ──────────────────────────────────────────────────────────────

    def _analyze_high_low(
        self,
        symbols: List[str],
        trade_date: str,
        kline_data: Dict[str, pd.DataFrame],
    ) -> Dict:
        """
        统计创 20/60/250 日新高、新低的股票数量。
        复用 MyTT.HHV / LLV 逻辑（直接用 pandas rolling 实现，避免导入依赖）。
        """
        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')

        new_high_20  = 0
        new_high_60  = 0
        new_high_250 = 0
        new_low_20   = 0
        new_low_60   = 0
        new_low_250  = 0

        for symbol in symbols:
            df = kline_data.get(symbol)
            if df is None or df.empty or 'close' not in df.columns:
                continue

            # 只取到 trade_date 为止的数据
            df_hist = df[df.index.normalize() <= target_dt].copy()
            if df_hist.empty:
                continue

            close_series = df_hist['close'].dropna()
            if len(close_series) < 2:
                continue

            today_close = close_series.iloc[-1]

            # 检查今日是否为 N 日新高/新低
            for n, high_counter, low_counter in [
                (20,  'new_high_20',  'new_low_20'),
                (60,  'new_high_60',  'new_low_60'),
                (250, 'new_high_250', 'new_low_250'),
            ]:
                if len(close_series) < n:
                    continue
                # 取前 n 日（不含今日）的最高/最低
                prev_n = close_series.iloc[-(n+1):-1] if len(close_series) > n else close_series.iloc[:-1]
                if prev_n.empty:
                    continue
                prev_high = prev_n.max()
                prev_low  = prev_n.min()

                if today_close > prev_high:
                    if high_counter == 'new_high_20':   new_high_20  += 1
                    elif high_counter == 'new_high_60':  new_high_60  += 1
                    else:                                new_high_250 += 1
                if today_close < prev_low:
                    if low_counter == 'new_low_20':   new_low_20  += 1
                    elif low_counter == 'new_low_60':  new_low_60  += 1
                    else:                              new_low_250 += 1

        return {
            'new_high_20':  new_high_20,
            'new_high_60':  new_high_60,
            'new_high_250': new_high_250,
            'new_low_20':   new_low_20,
            'new_low_60':   new_low_60,
            'new_low_250':  new_low_250,
        }


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    """安全转换为 float，None/NaN 返回 None"""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None
