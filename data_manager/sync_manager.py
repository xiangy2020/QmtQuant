"""
sync_manager - 项目数据同步状态管理器

负责维护同步状态元数据（最后同步时间、数据范围），
以及提供通用的 K 线数据写入接口。

存储路径（品类体系）：
  ~/.qmtquant/cache/stock/kline/sync_meta.parquet

已删除的旧接口（Win→Mac 专用）：
  - sync_from_windows()
  - batch_sync_from_windows()
  - load_all_sync_meta()
  这些接口已由 sync_pipeline.py 中的 MiniQMTSource → ParquetSink 管道替代。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

import pandas as pd

from .storage import get_default_storage, save_parquet, load_parquet

logger = logging.getLogger(__name__)

# 同步状态元数据 Parquet 路径（相对于缓存根目录）
_SYNC_META_PARQUET = "stock/kline/sync_meta.parquet"


# ------------------------------------------------------------------
# 同步状态元数据管理（Parquet）
# ------------------------------------------------------------------

def _load_sync_meta() -> Dict:
    """加载同步状态元数据，若文件不存在则返回空字典"""
    df = load_parquet(_SYNC_META_PARQUET)
    if df.empty:
        return {}
    # 将 DataFrame 转回 {key: dict} 格式
    return df.to_dict(orient="index")


def _save_sync_meta(meta: Dict):
    """持久化同步状态元数据"""
    if not meta:
        return
    df = pd.DataFrame.from_dict(meta, orient="index")
    df.index.name = "key"
    save_parquet(_SYNC_META_PARQUET, df)


def _meta_key(symbol: str, period: str) -> str:
    """生成元数据字典的键，如 '600000.SH__1d'"""
    return f"{symbol}__{period}"


# ------------------------------------------------------------------
# 通用 K 线数据写入接口（替代旧的 sync_from_windows）
# ------------------------------------------------------------------

def save_kline(
    symbol: str,
    period: str,
    df: pd.DataFrame,
    log_callback=None,
    asset_type: str = 'stock',
) -> bool:
    """
    将 K 线 DataFrame 写入本地 Parquet 缓存，并更新同步元数据。

    此函数由 sync_pipeline.py 中的 ParquetSink 调用，
    也可由其他模块直接调用。

    Args:
        symbol:       股票代码，如 '600000.SH'
        period:       数据周期，如 '1d'
        df:           待写入的 DataFrame（索引必须是 DatetimeIndex）
        log_callback: 可选的日志回调函数 callback(msg: str)
        asset_type:   一级品类标识，如 'stock'、'index'（默认 'stock'）

    Returns:
        True 表示写入成功，False 表示跳过或失败
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        logger.debug(f"save_kline 跳过：df 为空 [{symbol} {period}]")
        return False

    try:
        if asset_type == 'stock':
            storage = get_default_storage()
            success = storage.save(symbol, period, df)
        else:
            # 非 stock 品类：直接写入 {asset_type}/kline/{period}/{market}/{code}.parquet
            from .storage import save_parquet, _parse_symbol
            code, market = _parse_symbol(symbol)
            rel_path = f"{asset_type}/kline/{period}/{market}/{code}.parquet"
            success = save_parquet(rel_path, df)

        if success:
            # 更新同步元数据
            meta = _load_sync_meta()
            key = _meta_key(symbol, period)
            now = datetime.now()

            start_date = None
            end_date = None
            try:
                if isinstance(df.index, pd.DatetimeIndex):
                    start_date = str(df.index.min().date())
                    end_date = str(df.index.max().date())
            except Exception:
                pass

            meta[key] = {
                "symbol": symbol,
                "period": period,
                "last_sync": now.isoformat(),
                "data_start": start_date,
                "data_end": end_date,
                "record_count": len(df),
            }
            _save_sync_meta(meta)

            msg = f"✓ 已写入本地缓存 [{symbol} {period}]，共 {len(df)} 条记录"
            logger.info(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass
            return True
        else:
            msg = f"⚠ 写入本地缓存失败 [{symbol} {period}]，存储引擎返回 False"
            logger.warning(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass
            return False

    except Exception as e:
        msg = f"⚠ 写入本地缓存异常 [{symbol} {period}]：{e}"
        logger.warning(msg, exc_info=True)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass
        return False


def get_sync_status(symbol: str, period: str) -> Optional[Dict]:
    """
    查询指定股票和周期的最后同步状态。

    Args:
        symbol: 股票代码，如 '600000.SH'
        period: 数据周期，如 '1d'

    Returns:
        字典，包含：
          - symbol:       股票代码
          - period:       数据周期
          - last_sync:    最后同步时间（datetime）
          - data_start:   已同步数据的起始日期（str）
          - data_end:     已同步数据的结束日期（str）
          - record_count: 最后一次同步的记录数
        若从未同步则返回 None
    """
    try:
        meta = _load_sync_meta()
        key = _meta_key(symbol, period)
        entry = meta.get(key)
        if not entry:
            return None

        result = dict(entry)
        if result.get("last_sync"):
            try:
                result["last_sync"] = datetime.fromisoformat(result["last_sync"])
            except Exception:
                pass
        return result

    except Exception as e:
        logger.error(f"get_sync_status 失败：{symbol} {period}，错误：{e}", exc_info=True)
        return None


def get_all_sync_meta() -> Dict:
    """
    一次性加载全部同步元数据，供批量展示使用。

    Returns:
        原始元数据字典，key 格式为 '{symbol}__{period}'
    """
    return _load_sync_meta()
