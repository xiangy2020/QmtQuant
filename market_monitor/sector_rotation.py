"""
sector_rotation.py — 行业板块轮动分析

支持多种行业分类体系（通过 classification 参数指定前缀），计算：
  1. 每个行业当日等权平均涨跌幅（降序排列）
  2. 每个行业近 5/10/20 日累计等权平均涨跌幅
  3. 每个行业涨停/跌停/上涨/下跌家数
  4. 热点行业识别（涨停数最多的前 3 个）
  5. 行业量能比（当日总成交额 vs 近20日均值）

设计原则：
  - 等权平均：行业内所有有效成分股涨跌幅的算术平均
  - 停牌股和幽灵标的从行业计算中剔除
  - 涨跌停判断严格使用 up_stop_price / down_stop_price
  - 无合约信息时跳过该股的涨跌停判断
"""

import logging
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from .data_loader import DataLoader

logger = logging.getLogger(__name__)


class SectorRotation:
    """
    行业板块轮动分析器。

    analyze() 返回结构：
    {
        'trade_date':      str,         # 分析日期 YYYYMMDD
        'classification':  str,         # 行业分类前缀，如 'SW1'、'CSRC1'
        'sectors':         list[dict],  # 行业数据列表（按当日涨跌幅降序）
        'hot_sectors':     list[str],   # 热点行业名称（涨停数最多前3个）
    }

    每个行业 dict 结构：
    {
        'name':         str,    # 行业名称（去掉 SW1 前缀）
        'full_name':    str,    # 完整名称（含 SW1 前缀）
        'pct_chg_1d':   float,  # 当日等权平均涨跌幅（%）
        'pct_chg_5d':   float,  # 近5日累计等权平均涨跌幅（%）
        'pct_chg_10d':  float,  # 近10日累计等权平均涨跌幅（%）
        'pct_chg_20d':  float,  # 近20日累计等权平均涨跌幅（%）
        'up_count':     int,    # 上涨家数
        'down_count':   int,    # 下跌家数
        'flat_count':   int,    # 平盘家数
        'limit_up':     int,    # 涨停家数
        'limit_down':   int,    # 跌停家数
        'total':        int,    # 有效成分股总数
        'amount_today': float,  # 当日总成交额（亿元）
        'amount_avg20': float,  # 近20日均成交额（亿元）
        'amount_ratio': float,  # 量能比（当日/20日均值）
        'is_hot':       bool,   # 是否为热点行业
    }
    """

    def __init__(self, loader: DataLoader):
        self._loader = loader

    # 支持的分类前缀及其显示名称
    CLASSIFICATION_LABELS = {
        'SW1':   '申万一级行业',
        'SW2':   '申万二级行业',
        'SW3':   '申万三级行业',
        'CSRC1': '证监会一级行业',
        'CSRC2': '证监会二级行业',
    }

    def analyze(self, trade_date: str, classification: str = 'SW1') -> Dict[str, Any]:
        """
        执行行业板块轮动分析。

        Args:
            trade_date:     分析日期 YYYYMMDD
            classification: 行业分类前缀，默认 'SW1'（申万一级）
                            可选：'SW1' / 'SW2' / 'SW3' / 'CSRC1' / 'CSRC2'

        Returns:
            行业轮动分析结果字典
        """
        label = self.CLASSIFICATION_LABELS.get(classification, classification)
        logger.info(f"[SectorRotation] 开始行业轮动分析，日期={trade_date}，分类={label}")

        # ── 加载指定分类的行业列表 ────────────────────────────────
        sw1_sectors = self._loader.load_sectors_by_prefix(classification)
        if not sw1_sectors:
            logger.warning(f"[SectorRotation] 未找到 {label} 数据")
            return {'trade_date': trade_date, 'classification': classification, 'sectors': [], 'hot_sectors': []}

        # ── 加载合约信息（涨跌停价）──────────────────────────────
        instrument_df = self._loader.load_instrument_detail()

        # ── 确定 K 线加载范围（近20日需要约40个自然日）────────────
        start_date = self._loader.get_n_days_before(trade_date, 60)
        target_dt  = pd.to_datetime(trade_date, format='%Y%m%d')

        # ── 收集所有行业成分股（去重，批量加载 K 线）────────────
        all_symbols_set = set()
        sector_members: Dict[str, List[str]] = {}

        for sector_name in sw1_sectors:
            members = self._loader.load_sector_members(sector_name)
            sector_members[sector_name] = members
            all_symbols_set.update(members)

        all_symbols = list(all_symbols_set)
        self._loader._log(
            f"[SectorRotation] {label} {len(sw1_sectors)} 个，"
            f"去重后成分股 {len(all_symbols)} 只，加载 K 线..."
        )

        # ── 批量加载 K 线 ─────────────────────────────────────────
        kline_data = self._loader.load_stock_kline_batch(
            all_symbols, '1d', start_date=start_date, end_date=trade_date
        )

        # ── 逐行业计算 ────────────────────────────────────────────
        sector_results = []

        for sector_name in sw1_sectors:
            members = sector_members.get(sector_name, [])
            if not members:
                continue

            # 过滤停牌股和幽灵标的
            valid_members = self._loader.filter_valid_symbols(
                members, trade_date, kline_data
            )

            if not valid_members:
                continue

            result = self._analyze_sector(
                sector_name=sector_name,
                classification=classification,
                members=valid_members,
                trade_date=trade_date,
                target_dt=target_dt,
                kline_data=kline_data,
                instrument_df=instrument_df,
            )
            if result:
                sector_results.append(result)

        # ── 识别热点行业（涨停数最多前3个）──────────────────────
        hot_sectors = self._identify_hot_sectors(sector_results, top_n=3)
        hot_set = set(hot_sectors)

        for r in sector_results:
            r['is_hot'] = r['full_name'] in hot_set

        # ── 按当日涨跌幅降序排列 ──────────────────────────────────
        sector_results.sort(
            key=lambda x: x['pct_chg_1d'] if x['pct_chg_1d'] is not None else -999,
            reverse=True,
        )

        self._loader._log(
            f"[SectorRotation] 完成，{label} 共 {len(sector_results)} 个，"
            f"热点行业：{hot_sectors}"
        )

        return {
            'trade_date':     trade_date,
            'classification': classification,
            'sectors':        sector_results,
            'hot_sectors':    hot_sectors,
        }

    # ──────────────────────────────────────────────────────────────
    # 单行业分析
    # ──────────────────────────────────────────────────────────────

    def _analyze_sector(
        self,
        sector_name: str,
        classification: str,
        members: List[str],
        trade_date: str,
        target_dt: pd.Timestamp,
        kline_data: Dict[str, pd.DataFrame],
        instrument_df: pd.DataFrame,
    ) -> Optional[Dict]:
        """
        计算单个行业的各项指标。
        """
        # 动态剥离分类前缀，得到纯行业名称
        display_name = sector_name
        if sector_name.startswith(classification):
            display_name = sector_name[len(classification):].strip()

        # 收集各成分股当日数据
        pct_chg_list   = []   # 当日涨跌幅列表
        up_count       = 0
        down_count     = 0
        flat_count     = 0
        limit_up_count = 0
        limit_dn_count = 0
        amount_today   = 0.0

        # 收集历史成交额（用于计算近20日均值）
        # daily_amounts[day] = 该行业当日总成交额
        daily_amounts: Dict[pd.Timestamp, float] = {}

        for symbol in members:
            df = kline_data.get(symbol)
            if df is None or df.empty:
                continue

            # 取当日数据
            day_data = df[df.index.normalize() == target_dt]
            if day_data.empty:
                continue

            row       = day_data.iloc[0]
            close     = _safe_float(row.get('close'))
            pre_close = _safe_float(row.get('preClose'))
            amount    = _safe_float(row.get('amount'))

            if close is None or pre_close is None or pre_close == 0:
                continue

            pct = (close - pre_close) / pre_close * 100
            pct_chg_list.append(pct)

            if close > pre_close:
                up_count += 1
            elif close < pre_close:
                down_count += 1
            else:
                flat_count += 1

            # 涨跌停判断
            if not instrument_df.empty and symbol in instrument_df.index:
                inst      = instrument_df.loc[symbol]
                up_stop   = _safe_float(inst.get('up_stop_price'))
                down_stop = _safe_float(inst.get('down_stop_price'))
                if up_stop is not None and close >= up_stop:
                    limit_up_count += 1
                if down_stop is not None and close <= down_stop:
                    limit_dn_count += 1

            # 当日成交额
            if amount and amount > 0:
                amount_today += amount

            # 历史成交额（用于均值计算）
            for dt, hist_row in df.iterrows():
                day = dt.normalize()
                amt = _safe_float(hist_row.get('amount'))
                if amt and amt > 0:
                    daily_amounts[day] = daily_amounts.get(day, 0.0) + amt

        if not pct_chg_list:
            return None

        # ── 当日等权平均涨跌幅 ────────────────────────────────────
        pct_chg_1d = round(float(np.mean(pct_chg_list)), 2)

        # ── 近5/10/20日累计等权平均涨跌幅 ────────────────────────
        pct_chg_5d  = self._calc_period_return(members, kline_data, target_dt, 5)
        pct_chg_10d = self._calc_period_return(members, kline_data, target_dt, 10)
        pct_chg_20d = self._calc_period_return(members, kline_data, target_dt, 20)

        # ── 量能比 ────────────────────────────────────────────────
        amount_avg20, amount_ratio = self._calc_amount_ratio(
            daily_amounts, target_dt, amount_today
        )

        return {
            'name':         display_name,
            'full_name':    sector_name,
            'pct_chg_1d':   pct_chg_1d,
            'pct_chg_5d':   pct_chg_5d,
            'pct_chg_10d':  pct_chg_10d,
            'pct_chg_20d':  pct_chg_20d,
            'up_count':     up_count,
            'down_count':   down_count,
            'flat_count':   flat_count,
            'limit_up':     limit_up_count,
            'limit_down':   limit_dn_count,
            'total':        len(pct_chg_list),
            'amount_today': round(amount_today / 1e8, 2) if amount_today else None,
            'amount_avg20': round(amount_avg20 / 1e8, 2) if amount_avg20 else None,
            'amount_ratio': amount_ratio,
            'is_hot':       False,  # 后续统一设置
        }

    # ──────────────────────────────────────────────────────────────
    # 近N日累计涨跌幅
    # ──────────────────────────────────────────────────────────────

    def _calc_period_return(
        self,
        members: List[str],
        kline_data: Dict[str, pd.DataFrame],
        target_dt: pd.Timestamp,
        n_days: int,
    ) -> Optional[float]:
        """
        计算行业近 n_days 个交易日的累计等权平均涨跌幅。

        方法：取每只股票近 n_days 个交易日内的首日前收价和末日收盘价，
        计算区间涨跌幅，再等权平均。
        """
        returns = []

        for symbol in members:
            df = kline_data.get(symbol)
            if df is None or df.empty:
                continue

            # 取到 target_dt 为止的数据
            hist = df[df.index.normalize() <= target_dt].copy()
            hist = hist[hist['close'].notna()]

            if len(hist) < 2:
                continue

            # 取最近 n_days 条有效数据
            recent = hist.tail(n_days)
            if len(recent) < 2:
                continue

            # 区间起始前收价（第一条的 preClose）
            start_pre_close = _safe_float(recent.iloc[0].get('preClose'))
            end_close       = _safe_float(recent.iloc[-1].get('close'))

            if start_pre_close and start_pre_close > 0 and end_close:
                period_return = (end_close - start_pre_close) / start_pre_close * 100
                returns.append(period_return)

        if not returns:
            return None
        return round(float(np.mean(returns)), 2)

    # ──────────────────────────────────────────────────────────────
    # 量能比计算
    # ──────────────────────────────────────────────────────────────

    def _calc_amount_ratio(
        self,
        daily_amounts: Dict[pd.Timestamp, float],
        target_dt: pd.Timestamp,
        amount_today: float,
    ):
        """
        计算行业量能比（当日总成交额 / 近20日均值）。

        Returns:
            (amount_avg20, amount_ratio) 元组
        """
        if not daily_amounts or not amount_today:
            return None, None

        # 取 target_dt 之前的历史成交额
        sorted_days = sorted(d for d in daily_amounts.keys() if d < target_dt)
        if not sorted_days:
            return None, None

        recent_20 = sorted_days[-20:]
        avg_20 = float(np.mean([daily_amounts[d] for d in recent_20]))

        if avg_20 == 0:
            return None, None

        ratio = round(amount_today / avg_20, 2)
        return avg_20, ratio

    # ──────────────────────────────────────────────────────────────
    # 热点行业识别
    # ──────────────────────────────────────────────────────────────

    def _identify_hot_sectors(
        self,
        sector_results: List[Dict],
        top_n: int = 3,
    ) -> List[str]:
        """
        识别热点行业：当日涨停股数量最多的前 top_n 个行业。

        Returns:
            行业 full_name 列表（含 SW1 前缀）
        """
        # 过滤掉涨停数为0的行业
        with_limit_up = [r for r in sector_results if r.get('limit_up', 0) > 0]
        if not with_limit_up:
            return []

        # 按涨停数降序
        with_limit_up.sort(key=lambda x: x['limit_up'], reverse=True)
        return [r['full_name'] for r in with_limit_up[:top_n]]


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
