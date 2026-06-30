"""
data_manager/sync_pipeline.py — 数据同步框架

定义 SyncSource / SyncSink 抽象基类，以及第一期实现：
  - MiniQMTSource：从 miniQMT 本地缓存读取数据（不触发下载）
  - ParquetSink：写入 ~/.qmtquant/cache/ 对应路径

管道使用方式：
    from data_manager.sync_pipeline import SyncPipeline, MiniQMTSource, ParquetSink

    pipeline = SyncPipeline(
        source=MiniQMTSource(),
        sink=ParquetSink(),
    )
    result = pipeline.run(
        symbols=['600000.SH', '000001.SZ'],
        periods=['1d', '5m'],
        start_date='20200101',
        end_date='',
        on_progress=lambda done, total: ...,
        on_item=lambda symbol, period, ok, msg: ...,
    )

元数据同步（板块列表 / 成分股）：
    pipeline.sync_sector_list()
    pipeline.sync_sector_members(sector_name='沪深A股')
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 抽象基类
# ------------------------------------------------------------------

class SyncSource(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def get_kline(
        self,
        symbols: List[str],
        period: str,
        start_time: str = "19900101",
        end_time: str = "",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取 K 线数据。

        Args:
            symbols:    股票代码列表
            period:     数据周期，如 '1d'、'5m'
            start_time: 起始日期 YYYYMMDD，默认 '19900101'
            end_time:   结束日期 YYYYMMDD，默认 '' 表示最新

        Returns:
            {symbol: DataFrame} 字典，DataFrame 索引为 DatetimeIndex
        """

    @abstractmethod
    def get_stock_list(self, sector: str) -> List[str]:
        """获取板块成分股列表"""

    @abstractmethod
    def get_sector_list(self) -> List[str]:
        """获取所有板块名称列表"""


class SyncSink(ABC):
    """数据写入目标抽象基类"""

    @abstractmethod
    def write_kline(
        self,
        symbol: str,
        period: str,
        df: pd.DataFrame,
        log_callback: Optional[Callable] = None,
    ) -> bool:
        """写入 K 线数据"""

    @abstractmethod
    def write_sector_list(self, sectors: List[str]) -> bool:
        """写入板块列表"""

    @abstractmethod
    def write_sector_members(self, sector_name: str, members: List[str]) -> bool:
        """写入板块成分股"""


# ------------------------------------------------------------------
# MiniQMTSource：从 miniQMT 本地缓存读取（不触发下载）
# ------------------------------------------------------------------

class MiniQMTSource(SyncSource):
    """
    miniQMT 数据源。

    调用 xtdata.get_market_data_ex()（不加 sub 参数），
    纯读取 miniQMT 本地缓存，不触发券商服务器下载。
    """

    # 单批最多传入的股票数（避免单次请求数据量过大）
    BATCH_SIZE = 500

    def __init__(self):
        # 延迟导入，避免 env 未初始化时报错
        from env import xtdata as _xtdata
        self._xtdata = _xtdata

    def get_kline(
        self,
        symbols: List[str],
        period: str,
        start_time: str = "19900101",
        end_time: str = "",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取 K 线数据（分批调用，每批 BATCH_SIZE 只）。

        Returns:
            {symbol: DataFrame}，DataFrame 索引已转换为 DatetimeIndex
        """
        if self._xtdata is None:
            logger.error("MiniQMTSource: xtdata 未初始化")
            return {}

        result: Dict[str, pd.DataFrame] = {}

        for batch_start in range(0, len(symbols), self.BATCH_SIZE):
            batch = symbols[batch_start: batch_start + self.BATCH_SIZE]
            try:
                raw = self._xtdata.get_market_data_ex(
                    field_list=[],
                    stock_list=batch,
                    period=period,
                    start_time=start_time,
                    end_time=end_time,
                    dividend_type="none",
                    fill_data=True,
                )
                if raw:
                    for symbol, df in raw.items():
                        if df is None or (hasattr(df, "empty") and df.empty):
                            continue
                        df = self._normalize_index(df, symbol, period)
                        if df is not None and not df.empty:
                            result[symbol] = df
            except Exception as e:
                logger.warning(
                    f"MiniQMTSource.get_kline 批次失败 "
                    f"period={period} batch[{batch_start}]: {e}"
                )

        return result

    def get_stock_list(self, sector: str) -> List[str]:
        """获取板块成分股列表"""
        if self._xtdata is None:
            return []
        try:
            result = self._xtdata.get_stock_list_in_sector(sector)
            return result if result else []
        except Exception as e:
            logger.warning(f"MiniQMTSource.get_stock_list({sector!r}) 失败：{e}")
            return []

    def get_sector_list(self) -> List[str]:
        """获取所有板块名称列表（调用 xtdata.get_sector_list() 获取完整列表）"""
        if self._xtdata is None:
            logger.warning("MiniQMTSource.get_sector_list: xtdata 未初始化")
            return []
        try:
            result = self._xtdata.get_sector_list()
            if not result:
                logger.warning("MiniQMTSource.get_sector_list: xtdata.get_sector_list() 返回空列表")
                return []
            logger.info(f"MiniQMTSource.get_sector_list: 获取到 {len(result)} 个板块")
            return list(result)
        except Exception as e:
            logger.warning(f"MiniQMTSource.get_sector_list() 失败：{e}")
            return []

    @staticmethod
    def _normalize_index(df: pd.DataFrame, symbol: str, period: str) -> Optional[pd.DataFrame]:
        """
        将 miniQMT 返回的 DataFrame 索引统一转换为 DatetimeIndex。

        miniQMT 返回的索引可能是多种整数格式：
          - 8位  YYYYMMDD
          - 14位 YYYYMMDDHHMMSS
          - 13位 毫秒时间戳
        """
        try:
            df = df.copy()
            if isinstance(df.index, pd.DatetimeIndex):
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df if not df.empty else None

            # 整数时间戳：通过样本值位数判断格式
            raw = df.index.astype(float)
            sample = int(abs(raw[0])) if len(raw) > 0 else 0
            s = str(sample)

            if len(s) == 14:
                # YYYYMMDDHHMMSS
                df.index = pd.to_datetime(
                    df.index.astype(str).str[:14],
                    format="%Y%m%d%H%M%S",
                    errors="coerce",
                )
            elif len(s) == 8:
                # YYYYMMDD
                df.index = pd.to_datetime(
                    df.index.astype(str),
                    format="%Y%m%d",
                    errors="coerce",
                )
            elif sample > 1e12:
                # 13位毫秒时间戳
                df.index = (
                    pd.to_datetime(raw, unit="ms", utc=True)
                    .tz_convert("Asia/Shanghai")
                    .tz_localize(None)
                )
            elif sample > 1e9:
                # 10位秒时间戳
                df.index = (
                    pd.to_datetime(raw, unit="s", utc=True)
                    .tz_convert("Asia/Shanghai")
                    .tz_localize(None)
                )
            else:
                df.index = pd.to_datetime(df.index, errors="coerce")

            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # 过滤 NaT
            df = df[df.index.notna()]
            return df if not df.empty else None

        except Exception as e:
            logger.warning(f"_normalize_index 失败 [{symbol} {period}]：{e}")
            return None


# ------------------------------------------------------------------
# ParquetSink：写入 ~/.qmtquant/cache/
# ------------------------------------------------------------------

class ParquetSink(SyncSink):
    """
    Parquet 数据写入目标。

    K 线数据写入路径：~/.qmtquant/cache/{asset_type}/kline/{period}/{market}/{code}.parquet
    板块列表写入路径：~/.qmtquant/cache/stock/sector_list.parquet
    成分股写入路径：  ~/.qmtquant/cache/industry/members/{sector_name}.parquet
    """

    def __init__(self, asset_type: str = 'stock'):
        from .sync_manager import save_kline as _save_kline
        from .storage import save_parquet as _save_parquet
        self._save_kline = _save_kline
        self._save_parquet = _save_parquet
        self._asset_type = asset_type

    def write_kline(
        self,
        symbol: str,
        period: str,
        df: pd.DataFrame,
        log_callback: Optional[Callable] = None,
    ) -> bool:
        """写入 K 线数据，同时更新 sync_meta"""
        return self._save_kline(symbol, period, df, log_callback, self._asset_type)

    def write_sector_list(self, sectors: List[str]) -> bool:
        """写入板块列表到 industry/sector_list/sector_list.parquet"""
        if not sectors:
            return False
        df = pd.DataFrame({"sector_name": sectors})
        df["updated_at"] = datetime.now().isoformat()
        success = self._save_parquet("industry/sector_list/sector_list.parquet", df)
        if success:
            logger.info(f"板块列表已写入，共 {len(sectors)} 个板块")
        return success

    def write_sector_members(self, sector_name: str, members: List[str]) -> bool:
        """写入板块成分股到 industry/members/{sector_name}.parquet"""
        if not members:
            logger.debug(f"write_sector_members 跳过：{sector_name!r} 成分股为空")
            return False
        # 文件名中不能有特殊字符，用 _ 替换
        safe_name = sector_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        rel_path = f"industry/members/{safe_name}.parquet"
        df = pd.DataFrame({
            "symbol": members,
            "sector_name": sector_name,
            "updated_at": datetime.now().isoformat(),
        })
        success = self._save_parquet(rel_path, df)
        if success:
            logger.info(f"成分股已写入：{sector_name!r}，共 {len(members)} 只")
        return success


# ------------------------------------------------------------------
# SyncPipeline：管道编排
# ------------------------------------------------------------------

class SyncPipeline:
    """
    数据同步管道。

    将 SyncSource 和 SyncSink 组合，提供统一的同步入口。
    """

    def __init__(self, source: SyncSource, sink: SyncSink):
        self.source = source
        self.sink = sink

    def run(
        self,
        symbols: List[str],
        periods: List[str],
        start_date: str = "19900101",
        end_date: str = "",
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_item: Optional[Callable[[str, str, bool, str], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> Dict:
        """
        执行 K 线数据同步。

        Args:
            symbols:     股票代码列表
            periods:     数据周期列表，如 ['1d', '5m']
            start_date:  起始日期 YYYYMMDD
            end_date:    结束日期 YYYYMMDD，'' 表示最新
            on_progress: 进度回调 (done_count, total_count)
            on_item:     单条完成回调 (symbol, period, success, msg)
            stop_flag:   停止检查函数，返回 True 时停止

        Returns:
            {
                'success': int,   # 成功数
                'failed':  int,   # 失败数
                'skipped': int,   # 跳过数（数据为空）
                'elapsed': float, # 耗时（秒）
            }
        """
        total = len(symbols) * len(periods)
        done = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0
        start_time = time.perf_counter()

        for period in periods:
            if stop_flag and stop_flag():
                break

            # 批量从数据源获取
            logger.info(f"SyncPipeline: 开始同步周期 {period}，共 {len(symbols)} 只")
            fetched = self.source.get_kline(symbols, period, start_date, end_date)

            for symbol in symbols:
                if stop_flag and stop_flag():
                    break

                done += 1
                if on_progress:
                    on_progress(done, total)

                df = fetched.get(symbol)
                if df is None or (hasattr(df, "empty") and df.empty):
                    skipped_count += 1
                    msg = "数据源无数据"
                    if on_item:
                        on_item(symbol, period, False, msg)
                    continue

                ok = self.sink.write_kline(symbol, period, df)
                if ok:
                    success_count += 1
                    msg = f"✓ {len(df)} 条记录"
                else:
                    failed_count += 1
                    msg = "写入失败"

                if on_item:
                    on_item(symbol, period, ok, msg)

        elapsed = time.perf_counter() - start_time
        return {
            "success": success_count,
            "failed":  failed_count,
            "skipped": skipped_count,
            "elapsed": round(elapsed, 2),
        }

    def sync_sector_list(self) -> bool:
        """同步板块列表到 Parquet"""
        sectors = self.source.get_sector_list()
        if not sectors:
            logger.warning("sync_sector_list: 数据源返回空板块列表")
            return False
        return self.sink.write_sector_list(sectors)

    def sync_sector_members(self, sector_name: str) -> bool:
        """同步指定板块的成分股到 Parquet"""
        members = self.source.get_stock_list(sector_name)
        if not members:
            logger.warning(f"sync_sector_members: {sector_name!r} 成分股为空")
            return False
        return self.sink.write_sector_members(sector_name, members)

    def sync_all_sector_members(
        self,
        sectors: Optional[List[str]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Dict:
        """
        批量同步所有板块的成分股。

        Args:
            sectors:     板块列表，None 时从数据源获取
            on_progress: 进度回调

        Returns:
            {'success': int, 'failed': int}
        """
        if sectors is None:
            sectors = self.source.get_sector_list()

        success_count = 0
        failed_count = 0
        total = len(sectors)

        for idx, sector in enumerate(sectors):
            if on_progress:
                on_progress(idx + 1, total)
            ok = self.sync_sector_members(sector)
            if ok:
                success_count += 1
            else:
                failed_count += 1

        return {"success": success_count, "failed": failed_count}
