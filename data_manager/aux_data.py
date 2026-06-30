"""
aux_data - 项目辅助数据本地持久化模块

交易日历和合约基础信息统一纳入品类体系，存储路径：
  ~/.qmtquant/cache/stock/calendar/trading_calendar.parquet
  ~/.qmtquant/cache/stock/instrument/instrument_detail.parquet

本模块保留原有函数签名以兼容现有调用方，内部实现已切换为 Parquet 读写。
旧 JSON 文件（trading_calendar.json / instrument_detail.json）在系统启动时
由 migration.run_migrations() 自动迁移，迁移后旧文件被删除。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .storage import save_parquet, load_parquet

logger = logging.getLogger(__name__)

# 新 Parquet 相对路径（相对于 ~/.qmtquant/cache）
_TRADING_CALENDAR_PARQUET = "stock/calendar/trading_calendar.parquet"
_INSTRUMENT_DETAIL_PARQUET = "stock/instrument/instrument_detail.parquet"


# ──────────────────────────────────────────────────────────────────────────────
# 交易日历
# ──────────────────────────────────────────────────────────────────────────────

def save_trading_calendar(dates: List[str]) -> bool:
    """
    将交易日历列表全量覆盖写入 Parquet。

    Args:
        dates: 交易日历列表，元素格式为 'YYYY-MM-DD'（也兼容13位毫秒时间戳，会自动转换）

    Returns:
        True 表示写入成功，False 表示失败
    """
    if not dates:
        logger.debug("save_trading_calendar 跳过：dates 为空")
        return False

    # 防御性转换：统一转为 'YYYY-MM-DD' 格式，解析失败跳过（年份过滤由后续数据清洗处理）
    from datetime import datetime as _dt
    normalized: List[str] = []
    for val in dates:
        try:
            s = str(val).strip()
            if len(s) in (12, 13) and s.isdigit():
                # 12/13位均为毫秒时间戳 → 北京本地时间
                normalized.append(_dt.fromtimestamp(int(s) / 1000).strftime('%Y-%m-%d'))
            elif len(s) == 10 and s[4] == '-':
                # 已是 'YYYY-MM-DD'
                normalized.append(s)
            elif len(s) == 8 and s.isdigit():
                # 'YYYYMMDD'
                normalized.append(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        except Exception:
            pass

    # 去重并排序
    normalized = sorted(set(normalized))

    if not normalized:
        logger.warning("save_trading_calendar：转换后无有效日期，跳过写入")
        return False

    df = pd.DataFrame({"date": normalized})
    success = save_parquet(_TRADING_CALENDAR_PARQUET, df)
    if success:
        logger.info(f"交易日历已保存，共 {len(normalized)} 个交易日 → {_TRADING_CALENDAR_PARQUET}")
    return success


def load_trading_calendar() -> List[str]:
    """
    从 Parquet 读取交易日历列表。

    Returns:
        交易日历列表，元素格式为 'YYYY-MM-DD'；文件不存在则返回空列表
    """
    df = load_parquet(_TRADING_CALENDAR_PARQUET)
    if df.empty or "date" not in df.columns:
        return []
    return df["date"].tolist()


# ──────────────────────────────────────────────────────────────────────────────
# 合约基础信息
# ──────────────────────────────────────────────────────────────────────────────

def save_instrument_detail(detail_dict: Dict[str, dict]) -> bool:
    """
    将合约基础信息字典增量合并后写入 Parquet。
    新数据覆盖同 symbol 的旧数据，不删除其他 symbol 的数据。

    Args:
        detail_dict: {symbol: {open_date, expire_date, name, ...}} 格式的字典

    Returns:
        True 表示写入成功，False 表示失败
    """
    if not detail_dict:
        logger.debug("save_instrument_detail 跳过：detail_dict 为空")
        return False

    # 增量合并：先读取已有数据，再用新数据覆盖
    existing = load_instrument_detail()
    existing.update(detail_dict)

    df = pd.DataFrame.from_dict(existing, orient="index")
    df.index.name = "symbol"
    success = save_parquet(_INSTRUMENT_DETAIL_PARQUET, df)
    if success:
        logger.info(f"合约基础信息已保存，共 {len(existing)} 只股票 → {_INSTRUMENT_DETAIL_PARQUET}")
    return success


def load_instrument_detail() -> Dict[str, dict]:
    """
    从 Parquet 读取合约基础信息字典。

    Returns:
        {symbol: {...}} 格式的字典；文件不存在则返回空字典
    """
    df = load_parquet(_INSTRUMENT_DETAIL_PARQUET)
    if df.empty:
        return {}
    # 将 DataFrame 转回 {symbol: dict} 格式
    return df.to_dict(orient="index")


# ──────────────────────────────────────────────────────────────────────────────
# 指数基础信息
# ──────────────────────────────────────────────────────────────────────────────

# 指数基础信息 Parquet 路径（相对于 ~/.qmtquant/cache）
_INDEX_INSTRUMENT_DETAIL_PARQUET = "index/instrument/instrument_detail.parquet"


def save_index_instrument_detail(detail_dict: Dict[str, dict]) -> bool:
    """
    将指数基础信息字典增量合并后写入 Parquet。
    新数据覆盖同 symbol 的旧数据，不删除其他 symbol 的数据。

    存储路径：~/.qmtquant/cache/index/instrument/instrument_detail.parquet

    注意：保存 API 返回的全部字段，禁止在写入阶段裁剪字段。

    Args:
        detail_dict: {symbol: {字段名: 值, ...}} 格式的字典，字段来自 get_instrument_detail()

    Returns:
        True 表示写入成功，False 表示失败
    """
    if not detail_dict:
        logger.debug("save_index_instrument_detail 跳过：detail_dict 为空")
        return False

    # 增量合并：先读取已有数据，再用新数据覆盖
    existing = load_index_instrument_detail()
    existing.update(detail_dict)

    df = pd.DataFrame.from_dict(existing, orient="index")
    df.index.name = "symbol"
    success = save_parquet(_INDEX_INSTRUMENT_DETAIL_PARQUET, df)
    if success:
        logger.info(f"指数基础信息已保存，共 {len(existing)} 只指数 → {_INDEX_INSTRUMENT_DETAIL_PARQUET}")
    return success


def load_index_instrument_detail() -> Dict[str, dict]:
    """
    从 Parquet 读取指数基础信息字典。

    Returns:
        {symbol: {...}} 格式的字典；文件不存在则返回空字典
    """
    df = load_parquet(_INDEX_INSTRUMENT_DETAIL_PARQUET)
    if df.empty:
        return {}
    return df.to_dict(orient="index")


# ──────────────────────────────────────────────────────────────────────────────
# 幽灵标的判定
# ──────────────────────────────────────────────────────────────────────────────

def is_ghost_symbol(instrument_info: dict, asset_type: str = 'stock') -> bool:
    """
    判断是否为幽灵标的（open_date 和 expire_date 均缺失的非股票合约）。

    幽灵标的特征：
      - open_date 为 None 或空字符串
      - expire_date 为 None、0 或 99999999（无退市日）

    注意：
      - open_date 为 None 但 expire_date 有实际值的标的，属于"上市日期缺失"问题，
        不属于幽灵标的。
      - 当 asset_type='index' 时，open_date='0' 或空字符串属于正常情况（指数普遍
        没有上市日期），此时仅凭 open_date 缺失不能判定为幽灵标的，需要同时满足
        expire_date 也缺失才判定。实际上对指数而言，该函数逻辑与 stock 相同，
        但调用方应理解指数的 open_date 缺失是正常现象，不应将其过滤掉。

    Args:
        instrument_info: 合约信息字典，来自 get_instrument_detail() 或本地缓存
        asset_type:      一级品类标识，'stock' | 'index' 等；
                         当为 'index' 时，open_date='0' 视为正常（不触发幽灵判定）

    Returns:
        True 表示是幽灵标的，应跳过处理；False 表示正常标的
    """
    open_date   = instrument_info.get('open_date') or instrument_info.get('OpenDate')
    expire_date = instrument_info.get('expire_date') if 'expire_date' in instrument_info \
                  else instrument_info.get('ExpireDate')

    # 指数品类：open_date='0' 是正常情况，不触发幽灵判定
    if asset_type == 'index':
        # 指数只有在 expire_date 也缺失时才可能是幽灵标的，
        # 但由于指数本身就没有上市/退市日期，实际上不应过滤任何指数
        # 因此对 index 品类直接返回 False（不过滤）
        return False

    # stock 品类：open_date 和 expire_date 均缺失才是幽灵标的
    open_missing   = not open_date or str(open_date).strip() in ('', 'None', 'nan', '0')
    expire_missing = expire_date in (None, 0, 99999999) or \
                     str(expire_date).strip() in ('', 'None', 'nan', '0', '99999999')

    return open_missing and expire_missing
