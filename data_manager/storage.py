"""
Storage - 项目本地 Parquet 存储引擎

文件路径规则：
  ~/.qmtquant/cache/stock/kline/{period}/{market}/{code}.parquet
  例如：stock/kline/1d/SH/600000.parquet  （对应股票代码 600000.SH）
       stock/kline/1m/SZ/000001.parquet  （对应股票代码 000001.SZ）
"""

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# 缓存根目录（品类体系：stock 一级品类）
_DEFAULT_CACHE_ROOT = Path.home() / ".qmtquant" / "cache" / "stock"


def _parse_symbol(symbol: str):
    """
    解析股票代码，拆分为 (code, market)。

    支持格式：
      - '600000.SH'  → ('600000', 'SH')
      - '000001.SZ'  → ('000001', 'SZ')
      - '430047.BJ'  → ('430047', 'BJ')
    """
    parts = symbol.upper().split(".")
    if len(parts) != 2:
        raise ValueError(f"不支持的股票代码格式：{symbol}，期望格式如 '600000.SH'")
    code, market = parts
    return code, market


def _build_symbol(code: str, market: str) -> str:
    """将 code + market 还原为标准股票代码，如 '600000' + 'SH' → '600000.SH'"""
    return f"{code}.{market.upper()}"


class Storage:
    """
    项目本地 Parquet 存储引擎。

    负责将行情 DataFrame 以 Parquet 格式持久化到本地磁盘，
    并提供增量合并、按日期范围查询、文件信息查询等功能。
    """

    def __init__(self, cache_root: Optional[str] = None, compression: str = "snappy"):
        """
        初始化存储引擎。

        Args:
            cache_root: 缓存根目录，默认为 ~/.qmtquant/cache/
            compression: Parquet 压缩算法，默认 snappy
        """
        self.cache_root = Path(cache_root) if cache_root else _DEFAULT_CACHE_ROOT
        self.compression = compression
        # 确保根目录存在
        self.cache_root.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Storage 初始化，缓存根目录：{self.cache_root}")

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _get_file_path(self, symbol: str, period: str) -> Path:
        """
        根据股票代码和周期构建 Parquet 文件路径。

        例如：symbol='600000.SH', period='1d'
              → ~/.qmtquant/cache/kline/1d/SH/600000.parquet
        """
        code, market = _parse_symbol(symbol)
        return self.cache_root / "kline" / period / market / f"{code}.parquet"

    def _ensure_dir(self, file_path: Path):
        """确保文件所在目录存在"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 核心读写接口
    # ------------------------------------------------------------------

    def save(self, symbol: str, period: str, df: pd.DataFrame) -> bool:
        """
        将 DataFrame 写入本地 Parquet 缓存（增量合并去重）。

        若文件已存在，则与现有数据合并，按时间索引去重（保留最新数据），
        再重新写入。

        Args:
            symbol: 股票代码，如 '600000.SH'
            period: 数据周期，如 '1d'、'1m'、'5m'
            df:     待写入的 DataFrame，必须以时间为索引

        Returns:
            True 表示写入成功，False 表示失败
        """
        if df is None or df.empty:
            logger.debug(f"save 跳过：df 为空 [{symbol} {period}]")
            return False

        try:
            file_path = self._get_file_path(symbol, period)
            self._ensure_dir(file_path)

            # 规范化索引：调用方必须在传入前已将索引转为 DatetimeIndex
            # storage.save 不做格式猜测，避免整数时间戳被错误解析
            df = df.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                raise ValueError(
                    f"save 要求 DataFrame 索引必须是 DatetimeIndex，"
                    f"当前类型：{type(df.index)}，请在调用前先转换索引格式。"
                )
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df = df.sort_index()
            # 若文件已存在，增量合并
            if file_path.exists():
                existing = pd.read_parquet(file_path, engine="pyarrow")
                if not isinstance(existing.index, pd.DatetimeIndex):
                    existing.index = pd.to_datetime(existing.index)
                if existing.index.tz is not None:
                    existing.index = existing.index.tz_localize(None)

                combined = pd.concat([existing, df])
                # 去重：相同时间戳保留最新（来自 df 的数据）
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
            else:
                combined = df

            # 写入 Parquet
            combined.to_parquet(
                file_path,
                engine="pyarrow",
                compression=self.compression,
                index=True,
            )
            logger.debug(
                f"save 成功：{symbol} {period}，共 {len(combined)} 条记录 → {file_path}"
            )
            return True

        except Exception as e:
            logger.error(f"save 失败：{symbol} {period}，错误：{e}", exc_info=True)
            return False

    def load(
        self,
        symbol: str,
        period: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        从本地 Parquet 缓存读取数据。

        Args:
            symbol:     股票代码，如 '600000.SH'
            period:     数据周期，如 '1d'
            start_date: 起始日期（含），格式 'YYYYMMDD' 或 'YYYY-MM-DD'，None 表示不限
            end_date:   结束日期（含），格式同上，None 表示不限

        Returns:
            DataFrame，若文件不存在或无数据则返回空 DataFrame
        """
        try:
            file_path = self._get_file_path(symbol, period)
            if not file_path.exists():
                return pd.DataFrame()

            df = pd.read_parquet(file_path, engine="pyarrow")

            # Parquet 文件中的索引应已是 DatetimeIndex（由 save 保证）
            # 若不是，说明文件是旧版错误数据，记录警告
            if not isinstance(df.index, pd.DatetimeIndex):
                logger.warning(
                    f"load：{symbol} {period} 的 Parquet 索引不是 DatetimeIndex，"
                    f"类型为 {type(df.index)}，该文件可能是旧版错误数据，建议重新同步。"
                )
                df.index = pd.to_datetime(df.index, errors='coerce')
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            # 日期过滤
            if start_date:
                df = df[df.index >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df.index <= pd.to_datetime(end_date)]

            return df

        except Exception as e:
            logger.error(f"load 失败：{symbol} {period}，错误：{e}", exc_info=True)
            return pd.DataFrame()

    def delete(self, symbol: str, period: str) -> bool:
        """
        删除指定股票和周期的 Parquet 缓存文件。

        Args:
            symbol: 股票代码
            period: 数据周期

        Returns:
            True 表示删除成功（或文件本不存在），False 表示删除失败
        """
        try:
            file_path = self._get_file_path(symbol, period)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"delete 成功：{symbol} {period}")
            return True
        except Exception as e:
            logger.error(f"delete 失败：{symbol} {period}，错误：{e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 查询与统计接口
    # ------------------------------------------------------------------

    def list_symbols(self, period: str) -> List[str]:
        """
        列出指定周期下所有已缓存的股票代码。

        Args:
            period: 数据周期，如 '1d'

        Returns:
            股票代码列表，格式如 ['600000.SH', '000001.SZ']，按代码排序
        """
        try:
            period_dir = self.cache_root / "kline" / period
            if not period_dir.exists():
                return []

            symbols = []
            # 遍历市场子目录（SH/SZ/BJ 等）
            for market_dir in sorted(period_dir.iterdir()):
                if not market_dir.is_dir():
                    continue
                market = market_dir.name.upper()
                for parquet_file in sorted(market_dir.glob("*.parquet")):
                    code = parquet_file.stem
                    symbols.append(_build_symbol(code, market))

            return symbols

        except Exception as e:
            logger.error(f"list_symbols 失败：period={period}，错误：{e}", exc_info=True)
            return []

    def list_periods(self) -> List[str]:
        """
        列出所有已缓存的数据周期。

        Returns:
            周期列表，如 ['1d', '1m', '5m']
        """
        try:
            kline_dir = self.cache_root / "kline"
            if not kline_dir.exists():
                return []
            return sorted(
                d.name for d in kline_dir.iterdir() if d.is_dir()
            )
        except Exception as e:
            logger.error(f"list_periods 失败：{e}", exc_info=True)
            return []

    def get_info(self, symbol: str, period: str) -> Optional[Dict]:
        """
        获取指定股票缓存文件的详细信息。

        Args:
            symbol: 股票代码
            period: 数据周期

        Returns:
            字典，包含：
              - symbol:        股票代码
              - period:        数据周期
              - start_date:    数据起始日期（str）
              - end_date:      数据结束日期（str）
              - record_count:  记录数
              - file_size_mb:  文件大小（MB）
              - last_modified: 文件最后修改时间（datetime）
            若文件不存在则返回 None
        """
        try:
            file_path = self._get_file_path(symbol, period)
            if not file_path.exists():
                return None

            df = pd.read_parquet(file_path, engine="pyarrow")
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            stat = file_path.stat()
            return {
                "symbol": symbol,
                "period": period,
                "start_date": str(df.index.min().date()) if not df.empty else None,
                "end_date": str(df.index.max().date()) if not df.empty else None,
                "record_count": len(df),
                "file_size_mb": round(stat.st_size / (1024 * 1024), 4),
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
            }

        except Exception as e:
            logger.error(f"get_info 失败：{symbol} {period}，错误：{e}", exc_info=True)
            return None

    def exists(self, symbol: str, period: str) -> bool:
        """判断指定股票和周期的缓存文件是否存在"""
        return self._get_file_path(symbol, period).exists()

    def get_last_modified(self, symbol: str, period: str) -> Optional[datetime]:
        """
        获取缓存文件的最后修改时间。

        Returns:
            datetime 对象，若文件不存在则返回 None
        """
        file_path = self._get_file_path(symbol, period)
        if not file_path.exists():
            return None
        return datetime.fromtimestamp(file_path.stat().st_mtime)


# 模块级单例（供其他子模块直接使用）
_default_storage: Optional[Storage] = None


def get_default_storage() -> Storage:
    """获取模块级默认存储引擎单例（懒初始化）"""
    global _default_storage
    if _default_storage is None:
        _default_storage = Storage()
    return _default_storage


# ------------------------------------------------------------------
# 通用 Parquet 读写接口（用于非K线数据：交易日历、合约信息、sync_meta 等）
# ------------------------------------------------------------------

def _get_cache_root() -> Path:
    """获取缓存根目录"""
    return Path.home() / ".qmtquant" / "cache"


def save_parquet(rel_path: str, df: pd.DataFrame, cache_root: Optional[str] = None) -> bool:
    """
    将 DataFrame 写入指定相对路径的 Parquet 文件（全量覆盖）。

    Args:
        rel_path:   相对于缓存根目录的路径，如 'stock/calendar/trading_calendar.parquet'
        df:         待写入的 DataFrame
        cache_root: 缓存根目录，默认 ~/.qmtquant/cache

    Returns:
        True 表示写入成功，False 表示失败
    """
    if df is None or df.empty:
        logger.debug(f"save_parquet 跳过：df 为空 [{rel_path}]")
        return False
    try:
        root = Path(cache_root) if cache_root else _get_cache_root()
        file_path = root / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(file_path, engine="pyarrow", compression="snappy", index=True)
        logger.info(f"save_parquet 成功：{file_path}，共 {len(df)} 条记录")
        return True
    except Exception as e:
        logger.error(f"save_parquet 失败：{rel_path}，错误：{e}", exc_info=True)
        return False


def load_parquet(rel_path: str, cache_root: Optional[str] = None) -> pd.DataFrame:
    """
    从指定相对路径读取 Parquet 文件。

    Args:
        rel_path:   相对于缓存根目录的路径
        cache_root: 缓存根目录，默认 ~/.qmtquant/cache

    Returns:
        DataFrame，若文件不存在则返回空 DataFrame
    """
    try:
        root = Path(cache_root) if cache_root else _get_cache_root()
        file_path = root / rel_path
        if not file_path.exists():
            return pd.DataFrame()
        return pd.read_parquet(file_path, engine="pyarrow")
    except Exception as e:
        logger.error(f"load_parquet 失败：{rel_path}，错误：{e}", exc_info=True)
        return pd.DataFrame()


def parquet_exists(rel_path: str, cache_root: Optional[str] = None) -> bool:
    """判断指定相对路径的 Parquet 文件是否存在"""
    root = Path(cache_root) if cache_root else _get_cache_root()
    return (root / rel_path).exists()

