"""
data_loader.py — 市场监控数据加载公共层

封装从本地 Parquet 缓存加载各类数据的公共函数，供各子模块复用：
  - 股票 K 线（stock/kline/1d）
  - 指数 K 线（index/kline/1d）
  - 合约信息（stock/instrument）
  - 行业成分股（industry/members）

核心功能：
  - resolve_trade_date()：确定分析日期（自动取最新有效交易日）
  - load_stock_kline()：加载单只股票 K 线
  - load_index_kline()：加载单个指数 K 线
  - load_instrument_detail()：加载合约信息（含涨跌停价）
  - load_sector_members()：加载板块成分股列表
  - load_sw1_sectors()：加载申万一级行业列表（不含加权版）
  - filter_valid_symbols()：过滤停牌股 + 幽灵标的

设计原则：
  - 直接读取本地 Parquet 缓存，不发起任何网络请求
  - 单只股票文件不存在时跳过并记录日志，不中断整体流程
  - 幽灵标的过滤统一调用 data_manager.aux_data.is_ghost_symbol()
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from data_manager.storage import Storage
from data_manager.aux_data import is_ghost_symbol

logger = logging.getLogger(__name__)

# 缓存根目录
_CACHE_ROOT = Path.home() / ".qmtquant" / "cache"

# 指数 K 线使用独立的 Storage（指向 index/kline 目录）
_INDEX_CACHE_ROOT = _CACHE_ROOT / "index"


class DataLoader:
    """
    市场监控数据加载器。

    统一封装本地 Parquet 缓存的读取逻辑，供各子模块复用。
    """

    def __init__(self, callbacks=None):
        """
        Args:
            callbacks: ServiceCallbacks 实例，用于上报日志（可选）
        """
        self._cb = callbacks
        # 股票 K 线存储引擎
        self._stock_storage = Storage(cache_root=str(_CACHE_ROOT / "stock"))
        # 指数 K 线存储引擎（路径结构与股票相同，但根目录不同）
        self._index_storage = Storage(cache_root=str(_INDEX_CACHE_ROOT))
        # 合约信息缓存（懒加载）
        self._instrument_df: Optional[pd.DataFrame] = None

    def _log(self, msg: str) -> None:
        if self._cb:
            self._cb.on_log(msg)
        else:
            logger.debug(msg)

    # ──────────────────────────────────────────────────────────────
    # 交易日期解析
    # ──────────────────────────────────────────────────────────────

    def resolve_trade_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        确定分析日期。

        Args:
            date_str: 用户指定的日期（YYYYMMDD 格式），None 表示自动取最新有效交易日

        Returns:
            YYYYMMDD 格式的日期字符串；若无法确定则返回 None
        """
        if date_str:
            # 用户指定了日期，验证该日期在缓存中是否存在
            return self._validate_date_exists(date_str)
        else:
            # 自动取最新有效交易日
            return self._get_latest_trade_date()

    def _validate_date_exists(self, date_str: str) -> Optional[str]:
        """验证指定日期在股票 K 线缓存中是否存在数据"""
        try:
            # 扫描几只代表性股票确认日期存在
            probe_symbols = ['600000.SH', '000001.SZ', '000300.SH']
            target_dt = pd.to_datetime(date_str, format='%Y%m%d')

            for symbol in probe_symbols:
                try:
                    df = self._stock_storage.load(symbol, '1d',
                                                   start_date=date_str,
                                                   end_date=date_str)
                    if not df.empty:
                        return date_str
                except Exception:
                    continue

            # 探测股票都没有，尝试扫描 SH 目录找任意一只
            sh_dir = _CACHE_ROOT / "stock" / "kline" / "1d" / "SH"
            if sh_dir.exists():
                for parquet_file in list(sh_dir.glob("*.parquet"))[:10]:
                    try:
                        df = pd.read_parquet(parquet_file)
                        if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                            if target_dt in df.index:
                                return date_str
                    except Exception:
                        continue

            self._log(f"[DataLoader] 指定日期 {date_str} 在本地缓存中无数据")
            return None

        except Exception as e:
            logger.warning(f"[DataLoader] 验证日期 {date_str} 时出错：{e}")
            return None

    def _get_latest_trade_date(self) -> Optional[str]:
        """扫描本地缓存，获取最新有效交易日（YYYYMMDD 格式）"""
        try:
            # 扫描 SH 目录，取多只股票的最新日期中位数（避免个别停牌股影响）
            sh_dir = _CACHE_ROOT / "stock" / "kline" / "1d" / "SH"
            if not sh_dir.exists():
                return None

            latest_dates = []
            for parquet_file in list(sh_dir.glob("*.parquet"))[:50]:
                try:
                    df = pd.read_parquet(parquet_file)
                    if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                        # 过滤掉 close 为 NaN 的行（停牌/无效数据）
                        valid = df[df['close'].notna()] if 'close' in df.columns else df
                        if not valid.empty:
                            latest_dates.append(valid.index.max())
                except Exception:
                    continue

            if not latest_dates:
                return None

            # 取出现频率最高的最新日期（众数），避免个别股票数据超前
            from collections import Counter
            date_counts = Counter(latest_dates)
            most_common_date = date_counts.most_common(1)[0][0]
            return most_common_date.strftime('%Y%m%d')

        except Exception as e:
            logger.warning(f"[DataLoader] 获取最新交易日时出错：{e}")
            return None

    # ──────────────────────────────────────────────────────────────
    # 合约信息
    # ──────────────────────────────────────────────────────────────

    def load_instrument_detail(self) -> pd.DataFrame:
        """
        加载股票合约信息（含涨跌停价、名称、上市日期等）。

        Returns:
            DataFrame，以 symbol 为索引，包含：
              name, exchange_id, open_date, expire_date, pre_close,
              up_stop_price, down_stop_price, float_volume, total_volume,
              instrument_status, is_trading, product_type
            若文件不存在则返回空 DataFrame
        """
        if self._instrument_df is not None:
            return self._instrument_df

        instrument_path = _CACHE_ROOT / "stock" / "instrument" / "instrument_detail.parquet"
        if not instrument_path.exists():
            self._log("[DataLoader] 合约信息文件不存在，请先执行 sync --asset stock --sub instrument")
            self._instrument_df = pd.DataFrame()
            return self._instrument_df

        try:
            df = pd.read_parquet(instrument_path)
            self._instrument_df = df
            self._log(f"[DataLoader] 加载合约信息：{len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[DataLoader] 加载合约信息失败：{e}")
            self._instrument_df = pd.DataFrame()
            return self._instrument_df

    def get_instrument_info(self, symbol: str) -> Optional[dict]:
        """
        获取单只股票的合约信息字典。

        Returns:
            dict 或 None（不存在时）
        """
        df = self.load_instrument_detail()
        if df.empty or symbol not in df.index:
            return None
        row = df.loc[symbol]
        return row.to_dict()

    # ──────────────────────────────────────────────────────────────
    # 板块成分股
    # ──────────────────────────────────────────────────────────────

    def load_sector_members(self, sector_name: str) -> List[str]:
        """
        加载指定板块的成分股列表。

        Args:
            sector_name: 板块名称，如 '沪深A股'、'SW1电子'

        Returns:
            股票代码列表，如 ['600000.SH', '000001.SZ', ...]
        """
        members_path = _CACHE_ROOT / "industry" / "members" / f"{sector_name}.parquet"
        if not members_path.exists():
            self._log(f"[DataLoader] 板块成分股文件不存在：{sector_name}")
            return []

        try:
            df = pd.read_parquet(members_path)
            if 'symbol' not in df.columns:
                logger.warning(f"[DataLoader] 板块 {sector_name} 成分股文件缺少 symbol 列")
                return []
            symbols = df['symbol'].dropna().tolist()
            self._log(f"[DataLoader] 加载板块 {sector_name}：{len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"[DataLoader] 加载板块 {sector_name} 成分股失败：{e}")
            return []

    def load_sw1_sectors(self) -> List[str]:
        """
        加载申万一级行业列表（SW1 前缀，不含加权版）。

        Returns:
            行业名称列表，如 ['SW1电子', 'SW1医药生物', ...]
        """
        return self.load_sectors_by_prefix('SW1')

    def load_sectors_by_prefix(self, prefix: str) -> List[str]:
        """
        按前缀加载行业/分类列表（不含加权版）。

        支持的前缀（取决于本地缓存中实际存在的文件）：
          - 'SW1'   申万一级行业（28 个）
          - 'SW2'   申万二级行业（104 个）
          - 'SW3'   申万三级行业（227 个）
          - 'CSRC1' 证监会一级行业（19 个）
          - 'CSRC2' 证监会二级行业（81 个）

        Args:
            prefix: 分类前缀，如 'SW1'、'CSRC1'

        Returns:
            行业名称列表，如 ['SW1电子', 'SW1医药生物', ...]；
            前缀不存在时返回空列表
        """
        members_dir = _CACHE_ROOT / "industry" / "members"
        if not members_dir.exists():
            return []

        sectors = [
            f.stem for f in members_dir.glob(f"{prefix}*.parquet")
            if '加权' not in f.stem
        ]
        sectors.sort()
        self._log(f"[DataLoader] 分类 {prefix}：{len(sectors)} 个")
        return sectors

    # ──────────────────────────────────────────────────────────────
    # 股票 K 线
    # ──────────────────────────────────────────────────────────────

    def load_stock_kline(
        self,
        symbol: str,
        period: str = '1d',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载单只股票 K 线数据。

        Args:
            symbol:     股票代码，如 '600000.SH'
            period:     数据周期，默认 '1d'
            start_date: 起始日期 YYYYMMDD（可选）
            end_date:   结束日期 YYYYMMDD（可选）

        Returns:
            DataFrame（DatetimeIndex），文件不存在时返回空 DataFrame
        """
        try:
            return self._stock_storage.load(symbol, period, start_date, end_date)
        except Exception as e:
            logger.debug(f"[DataLoader] 加载 {symbol} K 线失败：{e}")
            return pd.DataFrame()

    def load_stock_kline_batch(
        self,
        symbols: List[str],
        period: str = '1d',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        批量加载多只股票 K 线数据。

        Args:
            symbols:    股票代码列表
            period:     数据周期，默认 '1d'
            start_date: 起始日期 YYYYMMDD（可选）
            end_date:   结束日期 YYYYMMDD（可选）

        Returns:
            dict: {symbol: DataFrame}，文件不存在的股票不在结果中
        """
        result = {}
        for symbol in symbols:
            df = self.load_stock_kline(symbol, period, start_date, end_date)
            if not df.empty:
                result[symbol] = df
        return result

    # ──────────────────────────────────────────────────────────────
    # 指数 K 线
    # ──────────────────────────────────────────────────────────────

    def load_index_kline(
        self,
        symbol: str,
        period: str = '1d',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载单个指数 K 线数据。

        Args:
            symbol:     指数代码，如 '000001.SH'（上证指数）、'000300.SH'（沪深300）
            period:     数据周期，默认 '1d'
            start_date: 起始日期 YYYYMMDD（可选）
            end_date:   结束日期 YYYYMMDD（可选）

        Returns:
            DataFrame（DatetimeIndex），文件不存在时返回空 DataFrame
        """
        try:
            return self._index_storage.load(symbol, period, start_date, end_date)
        except Exception as e:
            logger.debug(f"[DataLoader] 加载指数 {symbol} K 线失败：{e}")
            return pd.DataFrame()

    # ──────────────────────────────────────────────────────────────
    # 过滤逻辑
    # ──────────────────────────────────────────────────────────────

    def filter_valid_symbols(
        self,
        symbols: List[str],
        trade_date: str,
        kline_data: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> List[str]:
        """
        过滤停牌股和幽灵标的，返回有效股票列表。

        过滤规则：
          1. 幽灵标的：open_date 和 expire_date 均缺失（调用 is_ghost_symbol()）
          2. 停牌股：当日 K 线中 suspendFlag != 0

        Args:
            symbols:    待过滤的股票代码列表
            trade_date: 分析日期 YYYYMMDD
            kline_data: 已加载的 K 线数据字典（可选，传入可避免重复读取）

        Returns:
            过滤后的有效股票代码列表
        """
        instrument_df = self.load_instrument_detail()
        valid = []
        ghost_count = 0
        suspend_count = 0

        for symbol in symbols:
            # ── 幽灵标的过滤 ──────────────────────────────────────
            if not instrument_df.empty and symbol in instrument_df.index:
                info = instrument_df.loc[symbol].to_dict()
                if is_ghost_symbol(info, asset_type='stock'):
                    ghost_count += 1
                    continue
            # 合约信息不存在时不过滤（保守策略）

            # ── 停牌股过滤 ────────────────────────────────────────
            if kline_data is not None:
                df = kline_data.get(symbol)
            else:
                df = self.load_stock_kline(symbol, '1d',
                                           start_date=trade_date,
                                           end_date=trade_date)

            if df is not None and not df.empty:
                target_dt = pd.to_datetime(trade_date, format='%Y%m%d')
                # 取当日数据行
                day_data = df[df.index.normalize() == target_dt]
                if not day_data.empty and 'suspendFlag' in day_data.columns:
                    suspend_val = day_data['suspendFlag'].iloc[0]
                    if pd.notna(suspend_val) and suspend_val != 0:
                        suspend_count += 1
                        continue

            valid.append(symbol)

        if ghost_count or suspend_count:
            self._log(
                f"[DataLoader] 过滤：幽灵标的 {ghost_count} 只，停牌股 {suspend_count} 只，"
                f"剩余有效 {len(valid)} 只"
            )
        return valid

    def is_suspended(self, symbol: str, trade_date: str,
                     kline_data: Optional[Dict[str, pd.DataFrame]] = None) -> bool:
        """
        判断指定股票在指定日期是否停牌。

        Args:
            symbol:     股票代码
            trade_date: 分析日期 YYYYMMDD
            kline_data: 已加载的 K 线数据字典（可选）

        Returns:
            True 表示停牌，False 表示正常交易
        """
        if kline_data is not None:
            df = kline_data.get(symbol)
        else:
            df = self.load_stock_kline(symbol, '1d',
                                       start_date=trade_date,
                                       end_date=trade_date)

        if df is None or df.empty:
            return False

        target_dt = pd.to_datetime(trade_date, format='%Y%m%d')
        day_data = df[df.index.normalize() == target_dt]
        if day_data.empty or 'suspendFlag' not in day_data.columns:
            return False

        suspend_val = day_data['suspendFlag'].iloc[0]
        return pd.notna(suspend_val) and suspend_val != 0

    # ──────────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────────

    def calc_pct_change(self, close: float, pre_close: float) -> Optional[float]:
        """
        计算涨跌幅（%）。

        Args:
            close:     收盘价
            pre_close: 前收价

        Returns:
            涨跌幅百分比，如 5.23 表示涨 5.23%；pre_close 为 0 时返回 None
        """
        if not pre_close or pre_close == 0:
            return None
        return round((close - pre_close) / pre_close * 100, 2)

    def get_n_days_before(self, trade_date: str, n: int) -> str:
        """
        获取 trade_date 往前 n 个自然日的日期（YYYYMMDD 格式）。
        用于确定 K 线加载的起始日期（留足历史数据用于计算均线等指标）。

        Args:
            trade_date: 基准日期 YYYYMMDD
            n:          往前的自然日数

        Returns:
            YYYYMMDD 格式日期字符串
        """
        from datetime import datetime, timedelta
        dt = datetime.strptime(trade_date, '%Y%m%d')
        result = dt - timedelta(days=n)
        return result.strftime('%Y%m%d')
