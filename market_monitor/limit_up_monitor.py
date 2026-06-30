"""
limit_up_monitor.py — 涨停板/个股异动监控

每日收盘后识别以下个股异动信号：
  1. 涨停股列表（代码、名称、行业、涨跌幅、成交额、连板天数）
  2. 跌停股列表（字段同上）
  3. 炸板股（当日最高价 >= 涨停价 且 收盘价 < 涨停价）
  4. 量价异动股（成交量 > 近20日均量×2 且 收盘价突破近20日最高价）

设计原则：
  - 涨跌停判断严格使用 up_stop_price / down_stop_price，不用固定比例估算
  - 无合约信息（up_stop_price 为空）时跳过该股，不估算
  - 连板计算：遍历历史 K 线，统计连续涨停天数
  - 过滤停牌股和幽灵标的后再做识别
"""

import logging
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from .data_loader import DataLoader

logger = logging.getLogger(__name__)


class LimitUpMonitor:
    """
    涨停板/个股异动监控分析器。

    analyze() 返回结构：
    {
        'trade_date':    str,           # 分析日期 YYYYMMDD
        'limit_up':      list[dict],    # 涨停股列表
        'limit_down':    list[dict],    # 跌停股列表
        'broken_limit':  list[dict],    # 炸板股列表
        'volume_surge':  list[dict],    # 量价异动股列表
    }
    """

    def __init__(self, loader: DataLoader):
        self._loader = loader

    def analyze(self, trade_date: str, sector: str = '沪深A股') -> Dict[str, Any]:
        """
        执行涨停板/个股异动监控。

        Args:
            trade_date: 分析日期 YYYYMMDD
            sector:     股票池板块名称（默认 '沪深A股'）

        Returns:
            监控结果字典
        """
        logger.info(f"[LimitUpMonitor] 开始监控，日期={trade_date}，板块={sector}")

        # ── 加载股票池 ────────────────────────────────────────────
        all_symbols = self._loader.load_sector_members(sector)
        if not all_symbols:
            logger.warning(f"[LimitUpMonitor] 板块 {sector} 无成分股数据")
            return self._empty_result(trade_date)

        # ── 加载 K 线（需要足够历史数据用于连板和均量计算）────────
        # 连板最多统计 30 天，均量需要 20 天，共需约 70 个自然日
        start_date = self._loader.get_n_days_before(trade_date, 100)
        self._loader._log(f"[LimitUpMonitor] 加载股票 K 线，起始={start_date}，共 {len(all_symbols)} 只...")

        kline_data = self._loader.load_stock_kline_batch(
            all_symbols, '1d', start_date=start_date, end_date=trade_date
        )

        # ── 过滤停牌股和幽灵标的 ──────────────────────────────────
        valid_symbols = self._loader.filter_valid_symbols(
            all_symbols, trade_date, kline_data
        )

        # ── 加载合约信息 ──────────────────────────────────────────
        instrument_df = self._loader.load_instrument_detail()

        # ── 加载行业映射（symbol → SW1行业名称）──────────────────
        industry_map = self._build_industry_map()

        # ── 逐股分析 ──────────────────────────────────────────────
        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')

        limit_up_list    = []
        limit_down_list  = []
        broken_limit_list = []
        volume_surge_list = []

        for symbol in valid_symbols:
            df = kline_data.get(symbol)
            if df is None or df.empty:
                continue

            # 取当日数据
            day_data = df[df.index.normalize() == target_dt]
            if day_data.empty:
                continue

            row = day_data.iloc[0]
            close     = _safe_float(row.get('close'))
            high      = _safe_float(row.get('high'))
            pre_close = _safe_float(row.get('preClose'))
            volume    = _safe_float(row.get('volume'))
            amount    = _safe_float(row.get('amount'))

            if close is None or pre_close is None or pre_close == 0:
                continue

            # 涨跌幅
            pct_chg = round((close - pre_close) / pre_close * 100, 2)

            # 合约信息
            up_stop   = None
            down_stop = None
            name      = symbol
            if not instrument_df.empty and symbol in instrument_df.index:
                inst      = instrument_df.loc[symbol]
                up_stop   = _safe_float(inst.get('up_stop_price'))
                down_stop = _safe_float(inst.get('down_stop_price'))
                name      = str(inst.get('name', symbol))

            industry = industry_map.get(symbol, '—')

            # ── 涨停判断 ──────────────────────────────────────────
            if up_stop is not None and close >= up_stop:
                # 计算连板天数
                consec_days = self._calc_consecutive_limit_up(
                    symbol, df, target_dt, instrument_df
                )
                limit_up_list.append({
                    'symbol':       symbol,
                    'name':         name,
                    'industry':     industry,
                    'pct_chg':      pct_chg,
                    'amount':       round(amount / 1e4, 2) if amount else None,  # 万元
                    'consec_days':  consec_days,
                    'close':        close,
                    'up_stop':      up_stop,
                })

            # ── 跌停判断 ──────────────────────────────────────────
            elif down_stop is not None and close <= down_stop:
                limit_down_list.append({
                    'symbol':   symbol,
                    'name':     name,
                    'industry': industry,
                    'pct_chg':  pct_chg,
                    'amount':   round(amount / 1e4, 2) if amount else None,
                    'close':    close,
                    'down_stop': down_stop,
                })

            # ── 炸板判断（曾触及涨停价但未封板）────────────────────
            if (up_stop is not None
                    and high is not None
                    and high >= up_stop
                    and close < up_stop):
                broken_limit_list.append({
                    'symbol':   symbol,
                    'name':     name,
                    'industry': industry,
                    'pct_chg':  pct_chg,
                    'high':     high,
                    'close':    close,
                    'up_stop':  up_stop,
                })

            # ── 量价异动判断 ──────────────────────────────────────
            if volume is not None:
                surge = self._check_volume_surge(symbol, df, target_dt, volume, close)
                if surge:
                    volume_surge_list.append({
                        'symbol':    symbol,
                        'name':      name,
                        'industry':  industry,
                        'pct_chg':   pct_chg,
                        'vol_ratio': surge['vol_ratio'],
                        'amount':    round(amount / 1e4, 2) if amount else None,
                        'close':     close,
                    })

        # ── 排序 ──────────────────────────────────────────────────
        # 涨停：连板天数降序
        limit_up_list.sort(key=lambda x: x['consec_days'], reverse=True)
        # 跌停：涨跌幅升序（跌幅最大在前）
        limit_down_list.sort(key=lambda x: x['pct_chg'])
        # 炸板：涨跌幅降序
        broken_limit_list.sort(key=lambda x: x['pct_chg'], reverse=True)
        # 量价异动：量比降序
        volume_surge_list.sort(key=lambda x: x['vol_ratio'], reverse=True)

        self._loader._log(
            f"[LimitUpMonitor] 涨停={len(limit_up_list)}，跌停={len(limit_down_list)}，"
            f"炸板={len(broken_limit_list)}，量价异动={len(volume_surge_list)}"
        )

        return {
            'trade_date':    trade_date,
            'limit_up':      limit_up_list,
            'limit_down':    limit_down_list,
            'broken_limit':  broken_limit_list,
            'volume_surge':  volume_surge_list,
        }

    # ──────────────────────────────────────────────────────────────
    # 连板计算
    # ──────────────────────────────────────────────────────────────

    def _calc_consecutive_limit_up(
        self,
        symbol: str,
        df: pd.DataFrame,
        target_dt: pd.Timestamp,
        instrument_df: pd.DataFrame,
    ) -> int:
        """
        计算连续涨停天数（含当日）。

        从当日往前遍历历史 K 线，判断每日是否涨停。
        由于历史涨停价可能与当日不同，此处用涨跌幅 >= 9.8% 作为历史涨停的近似判断
        （当日涨停已由 up_stop_price 精确判断，历史日期用涨幅近似）。

        Returns:
            连续涨停天数（含当日），最小为 1
        """
        # 取到 target_dt 为止的数据，按时间倒序
        hist = df[df.index.normalize() <= target_dt].copy()
        if hist.empty:
            return 1

        hist = hist.sort_index(ascending=False)

        consec = 0
        for i, (dt, row) in enumerate(hist.iterrows()):
            close     = _safe_float(row.get('close'))
            pre_close = _safe_float(row.get('preClose'))

            if close is None or pre_close is None or pre_close == 0:
                break

            pct = (close - pre_close) / pre_close * 100

            if i == 0:
                # 当日：已确认涨停（调用方已判断），直接计入
                consec += 1
            else:
                # 历史日：用涨幅 >= 9.8% 近似判断（兼容 ST 股 5% 涨停）
                # 注意：ST 股涨停约 5%，普通股约 10%，科创板/创业板约 20%
                # 此处用 4.8% 作为最低阈值，避免漏判 ST 股
                if pct >= 4.8:
                    consec += 1
                else:
                    break

        return max(consec, 1)

    # ──────────────────────────────────────────────────────────────
    # 量价异动检测
    # ──────────────────────────────────────────────────────────────

    def _check_volume_surge(
        self,
        symbol: str,
        df: pd.DataFrame,
        target_dt: pd.Timestamp,
        today_volume: float,
        today_close: float,
    ) -> Optional[Dict]:
        """
        检测量价异动：成交量 > 近20日均量×2 且 收盘价突破近20日最高价。

        Returns:
            dict {'vol_ratio': float} 或 None（不满足条件时）
        """
        # 取 target_dt 之前的历史数据
        hist = df[df.index.normalize() < target_dt].copy()
        if len(hist) < 5:  # 历史数据不足，跳过
            return None

        # 近20日均量
        recent = hist.tail(20)
        avg_vol = recent['volume'].dropna()
        if avg_vol.empty or avg_vol.mean() == 0:
            return None
        avg_volume = float(avg_vol.mean())

        # 量比
        vol_ratio = round(today_volume / avg_volume, 2)
        if vol_ratio < 2.0:
            return None

        # 近20日最高收盘价
        recent_high = recent['close'].dropna()
        if recent_high.empty:
            return None
        max_close_20d = float(recent_high.max())

        # 收盘价突破近20日最高价
        if today_close <= max_close_20d:
            return None

        return {'vol_ratio': vol_ratio}

    # ──────────────────────────────────────────────────────────────
    # 行业映射
    # ──────────────────────────────────────────────────────────────

    def _build_industry_map(self) -> Dict[str, str]:
        """
        构建 symbol → 申万一级行业名称 的映射字典。
        """
        industry_map = {}
        sw1_sectors = self._loader.load_sw1_sectors()

        for sector_name in sw1_sectors:
            members = self._loader.load_sector_members(sector_name)
            # 去掉 SW1 前缀作为显示名称
            display_name = sector_name.replace('SW1', '').strip()
            for symbol in members:
                industry_map[symbol] = display_name

        return industry_map

    # ──────────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_result(trade_date: str) -> Dict:
        return {
            'trade_date':    trade_date,
            'limit_up':      [],
            'limit_down':    [],
            'broken_limit':  [],
            'volume_surge':  [],
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
