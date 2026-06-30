"""
cache_manager - 项目缓存生命周期管理

提供缓存统计、校验、清理等管理功能，
供缓存统计和清空缓存调用。
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .storage import get_default_storage


def _norm_cal_date(val) -> Optional[str]:
    """
    将交易日历中的单个元素统一转为 'YYYY-MM-DD' 字符串。
    兼容：
      - 已是 'YYYY-MM-DD' 字符串
      - 12/13位毫秒时间戳（int 或 str，xtdata.get_trading_dates 实际返回格式）
    解析失败返回 None，不做年份过滤（异常值由后续数据清洗处理）。
    """
    try:
        s = str(val).strip()
        if len(s) in (12, 13) and s.isdigit():
            # 12/13位均为毫秒时间戳 → 本地时间（北京时间），禁用 utc
            return datetime.fromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
        if len(s) == 10 and s[4] == '-':
            # 已是 'YYYY-MM-DD'
            return s
        return None
    except Exception:
        return None

logger = logging.getLogger(__name__)

# 缓存根目录下的 kline 子目录
_KLINE_DIR_NAME = "kline"

# 缓存大小警告阈值（字节），默认 5GB
_WARN_SIZE_BYTES = 5 * 1024 * 1024 * 1024


# ------------------------------------------------------------------
# 统计接口
# ------------------------------------------------------------------

def get_statistics() -> Dict:
    """
    获取本地缓存的整体统计信息。

    Returns:
        字典，包含：
          - cache_root:      缓存根目录路径（str）
          - total_size_mb:   总缓存大小（MB）
          - total_size_bytes: 总缓存大小（字节，用于阈值判断）
          - asset_types:     一级品类统计，格式：
              {
                'stock': {
                    'display_name': '股票数据',
                    'enabled': True,
                    'size_mb': 161.6,
                    'symbol_count': 5148,   # K线子类的股票数（无K线则为0）
                    'start_date': '1970-01-01',
                    'end_date':   '2026-05-21',
                    'last_sync':  '2026-05-23 14:50',
                    'periods': {'1d': {...}, ...},  # 该品类下各周期明细
                },
                ...
              }
          - periods:         各周期统计（兼容旧格式，stock 品类的 K 线汇总）
          - global_start_date: 全局最早数据日期（str 或 None）
          - global_end_date:   全局最新数据日期（str 或 None）
          - warn_threshold_gb: 警告阈值（GB）
          - is_over_threshold: 是否超过警告阈值（bool）
          - aux_data:          辅助数据状态，格式：
              {
                'calendar_count':    8000,          # 交易日历条数（0 表示未同步）
                'calendar_range':    '1990-12-19 ~ 2025-05-20',  # 日历范围（str 或 None）
                'instrument_count':  5000,          # 合约信息条数（0 表示未同步）
              }
    """
    # 缓存根目录应为 ~/.qmtquant/cache，而非 storage.cache_root（后者是 stock 子目录）
    # 注意：不通过 env.get_cache_root() 获取，避免触发 xqshare 连接（env.py 顶层会尝试连接）
    cache_root = Path.home() / ".qmtquant" / "cache"

    stats: Dict = {
        "cache_root": str(cache_root),
        "total_size_mb": 0.0,
        "total_size_bytes": 0,
        "asset_types": {},
        "periods": {},
        "global_start_date": None,
        "global_end_date": None,
        "warn_threshold_gb": _WARN_SIZE_BYTES / (1024 ** 3),
        "is_over_threshold": False,
        "aux_data": {
            "calendar_count": 0,
            "calendar_range": None,
            "instrument_count": 0,
        },
    }

    # ── 辅助数据状态 ──────────────────────────────────────────────
    try:
        from .aux_data import load_trading_calendar, load_instrument_detail
        cal = load_trading_calendar()
        stats["aux_data"]["calendar_count"] = len(cal)
        if cal:
            cal_start = _norm_cal_date(cal[0])
            cal_end   = _norm_cal_date(cal[-1])
            if cal_start and cal_end:
                stats["aux_data"]["calendar_range"] = f"{cal_start} ~ {cal_end}"
        detail = load_instrument_detail()
        stats["aux_data"]["instrument_count"] = len(detail)
    except Exception as e:
        logger.debug(f"get_statistics 辅助数据读取失败（非致命）：{e}")

    # ── 同步元数据（用于获取各周期最后同步时间）────────────────────
    sync_meta: Dict = {}
    try:
        from .sync_manager import get_all_sync_meta
        sync_meta = get_all_sync_meta()
    except Exception as e:
        logger.debug(f"get_statistics 读取 sync_meta 失败（非致命）：{e}")

    all_start_dates: List[str] = []
    all_end_dates: List[str] = []
    total_bytes = 0

    # ── 一级品类统计 ──────────────────────────────────────────────
    try:
        from .asset_types import ALL_ASSET_TYPES
        for at_cfg in ALL_ASSET_TYPES:
            at_key = at_cfg.asset_type
            at_dir = cache_root / at_key
            at_entry: Dict = {
                "display_name": at_cfg.display_name,
                "enabled": at_cfg.enabled,
                "size_mb": 0.0,
                "symbol_count": 0,
                "start_date": None,
                "end_date": None,
                "last_sync": None,
                "periods": {},
                "sub_types": {},   # 二级子类明细：{sub_type: {display_name, size_mb, file_count, record_count}}
            }

            if not at_dir.exists():
                stats["asset_types"][at_key] = at_entry
                continue

            at_bytes = 0
            at_start_dates: List[str] = []
            at_end_dates: List[str] = []

            # 遍历该品类下所有子类目录
            for sub_dir in sorted(at_dir.iterdir()):
                if not sub_dir.is_dir():
                    continue
                sub_type = sub_dir.name

                # kline 子类：按周期统计股票数/大小/日期范围
                if sub_type == "kline":
                    for period_dir in sorted(sub_dir.iterdir()):
                        if not period_dir.is_dir():
                            continue
                        period = period_dir.name
                        period_bytes = 0
                        symbol_count = 0
                        period_start_dates: List[str] = []
                        period_end_dates: List[str] = []

                        for market_dir in period_dir.iterdir():
                            if not market_dir.is_dir():
                                continue
                            for parquet_file in market_dir.glob("*.parquet"):
                                period_bytes += parquet_file.stat().st_size
                                symbol_count += 1
                                try:
                                    df = pd.read_parquet(parquet_file, engine="pyarrow")
                                    if not df.empty:
                                        if not isinstance(df.index, pd.DatetimeIndex):
                                            df.index = pd.to_datetime(df.index)
                                        s = str(df.index.min().date())
                                        e = str(df.index.max().date())
                                        period_start_dates.append(s)
                                        period_end_dates.append(e)
                                        at_start_dates.append(s)
                                        at_end_dates.append(e)
                                        all_start_dates.append(s)
                                        all_end_dates.append(e)
                                except Exception:
                                    pass

                        period_mb = round(period_bytes / (1024 * 1024), 2)

                        # 从 sync_meta 中找该周期最新的 last_sync
                        period_last_sync = None
                        for key, entry in sync_meta.items():
                            if isinstance(entry, dict) and entry.get("period") == period:
                                raw = entry.get("last_sync")
                                if raw:
                                    try:
                                        from datetime import datetime as _dt
                                        t = _dt.fromisoformat(str(raw)) if isinstance(raw, str) else raw
                                        t_str = t.strftime("%Y-%m-%d %H:%M:%S")
                                        if period_last_sync is None or t_str > period_last_sync:
                                            period_last_sync = t_str
                                    except Exception:
                                        pass

                        at_entry["periods"][period] = {
                            "symbol_count": symbol_count,
                            "size_mb": period_mb,
                            "start_date": min(period_start_dates) if period_start_dates else None,
                            "end_date": max(period_end_dates) if period_end_dates else None,
                            "last_sync": period_last_sync,
                        }
                        at_bytes += period_bytes
                        at_entry["symbol_count"] += symbol_count

                        # 更新品类级 last_sync
                        if period_last_sync:
                            if at_entry["last_sync"] is None or period_last_sync > at_entry["last_sync"]:
                                at_entry["last_sync"] = period_last_sync

                    # kline 子类汇总写入 sub_types
                    sub_cfg = at_cfg.get_sub_type("kline")
                    sub_display = sub_cfg.display_name if sub_cfg else "K线行情"
                    kline_symbol_count = at_entry["symbol_count"]
                    kline_size_mb = round(at_bytes / (1024 * 1024), 2)
                    at_entry["sub_types"]["kline"] = {
                        "display_name": sub_display,
                        "size_mb": kline_size_mb,
                        "file_count": kline_symbol_count,
                        "record_count": None,   # K线不逐文件统计记录数（太慢），用 symbol_count 代替
                        "symbol_count": kline_symbol_count,
                        "periods": list(at_entry["periods"].keys()),
                    }
                else:
                    # 非 kline 子类：统计文件数、记录数、大小
                    sub_bytes = 0
                    sub_file_count = 0
                    sub_record_count = 0
                    # members 子类额外维护逐板块明细列表
                    sectors: List[Dict] = []
                    for f in sub_dir.rglob("*.parquet"):
                        sub_bytes += f.stat().st_size
                        sub_file_count += 1
                        file_size_mb = round(f.stat().st_size / (1024 * 1024), 4)
                        # 文件修改时间作为 last_sync
                        try:
                            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            mtime = None
                        if sub_type == "members":
                            # 每个文件对应一个板块，文件名（去掉 .parquet 后缀）即为板块名称
                            sector_name = f.stem
                            # 加权板块过滤：不在树形表格中展示
                            if sector_name.endswith("加权"):
                                try:
                                    df = pd.read_parquet(f, engine="pyarrow")
                                    sub_record_count += len(df)
                                except Exception:
                                    pass
                                continue
                            sector_entry: Dict = {
                                "name": sector_name,
                                "symbol_count": 0,
                                "size_mb": file_size_mb,
                                "last_sync": mtime,
                                # _stocks 为内部字段，用于推断父子关系，最终不写入输出
                                "_stocks": set(),
                            }
                            try:
                                df = pd.read_parquet(f, engine="pyarrow")
                                sector_entry["symbol_count"] = len(df)
                                sub_record_count += len(df)
                                # 收集成分股集合（取第一列），用于父子关系推断
                                if not df.empty:
                                    sector_entry["_stocks"] = set(df.iloc[:, 0].dropna().tolist())
                            except Exception as e:
                                sector_entry["error"] = str(e)
                            sectors.append(sector_entry)
                        else:
                            try:
                                df = pd.read_parquet(f, engine="pyarrow")
                                sub_record_count += len(df)
                            except Exception:
                                pass
                    at_bytes += sub_bytes
                    # 无数据时不写入 sub_types，CLI 中显示为"未同步"
                    if sub_file_count == 0:
                        continue
                    # 查找该子类的 display_name
                    sub_cfg = at_cfg.get_sub_type(sub_type)
                    sub_display = sub_cfg.display_name if sub_cfg else sub_type
                    sub_entry: Dict = {
                        "display_name": sub_display,
                        "size_mb": round(sub_bytes / (1024 * 1024), 2),
                        "file_count": sub_file_count,
                        "record_count": sub_record_count,
                    }
                    # members 子类：构建父子关系并附加逐板块明细
                    if sub_type == "members":
                        # 构建父子关系映射
                        try:
                            parent_map = _build_sector_parent_map(sectors)
                        except Exception as e:
                            logger.warning(f"构建板块父子关系失败（非致命）：{e}")
                            parent_map = {}
                        # 填充 parent 字段，移除内部字段 _stocks
                        for s in sectors:
                            s["parent"] = parent_map.get(s["name"], None)
                            s.pop("_stocks", None)
                        # 注入虚拟顶层节点（申万行业 / 证监会行业）
                        # 仅当 parent_map 中存在对应 key 时才注入（说明有子节点）
                        virtual_nodes = []
                        for vname in ("申万行业", "证监会行业", "期货"):
                            if vname in parent_map:
                                virtual_nodes.append({
                                    "name":         vname,
                                    "parent":       None,
                                    "symbol_count": 0,
                                    "size_mb":      0,
                                    "last_sync":    None,
                                    "is_virtual":   True,   # 标记为虚拟节点
                                })
                        sectors = virtual_nodes + sectors
                        sectors.sort(key=lambda x: x["name"])
                        sub_entry["sectors"] = sectors
                    at_entry["sub_types"][sub_type] = sub_entry

            at_entry["size_mb"] = round(at_bytes / (1024 * 1024), 2)
            if at_start_dates:
                at_entry["start_date"] = min(at_start_dates)
            if at_end_dates:
                at_entry["end_date"] = max(at_end_dates)

            total_bytes += at_bytes
            stats["asset_types"][at_key] = at_entry

    except Exception as e:
        logger.error(f"get_statistics 品类统计失败：{e}", exc_info=True)

    stats["total_size_bytes"] = total_bytes
    stats["total_size_mb"] = round(total_bytes / (1024 * 1024), 2)
    stats["is_over_threshold"] = total_bytes >= _WARN_SIZE_BYTES

    if all_start_dates:
        stats["global_start_date"] = min(all_start_dates)
    if all_end_dates:
        stats["global_end_date"] = max(all_end_dates)

    return stats


# ------------------------------------------------------------------
# 校验接口
# ------------------------------------------------------------------

def validate_cache(symbol: str, period: str) -> Dict:
    """
    校验指定股票缓存文件的完整性（是否可正常读取）。

    Args:
        symbol: 股票代码，如 '600000.SH'
        period: 数据周期，如 '1d'

    Returns:
        字典，包含：
          - symbol:   股票代码
          - period:   数据周期
          - exists:   文件是否存在（bool）
          - readable: 文件是否可正常读取（bool）
          - record_count: 记录数（int，读取失败时为 0）
          - error:    错误信息（str 或 None）
    """
    storage = get_default_storage()
    file_path = storage._get_file_path(symbol, period)

    result = {
        "symbol": symbol,
        "period": period,
        "exists": file_path.exists(),
        "readable": False,
        "record_count": 0,
        "error": None,
    }

    if not result["exists"]:
        return result

    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
        result["readable"] = True
        result["record_count"] = len(df)
    except Exception as e:
        result["readable"] = False
        result["error"] = str(e)
        logger.warning(f"validate_cache 文件损坏：{symbol} {period}，错误：{e}")

    return result


# ------------------------------------------------------------------
# 清理接口
# ------------------------------------------------------------------

def clear_all() -> Dict:
    """
    清空所有本地 Parquet 缓存（删除 kline 目录下所有文件）。

    同时清除同步元数据文件。

    Returns:
        字典，包含：
          - success:        是否成功（bool）
          - deleted_files:  删除的文件数量
          - freed_mb:       释放的磁盘空间（MB）
          - error:          错误信息（str 或 None）
    """
    storage = get_default_storage()
    kline_dir = storage.cache_root / _KLINE_DIR_NAME

    result = {
        "success": False,
        "deleted_files": 0,
        "freed_mb": 0.0,
        "error": None,
    }

    try:
        total_bytes = 0
        deleted_count = 0

        if kline_dir.exists():
            # 统计待删除文件
            for f in kline_dir.rglob("*.parquet"):
                total_bytes += f.stat().st_size
                deleted_count += 1

            # 删除整个 kline 目录
            shutil.rmtree(kline_dir)
            logger.info(f"clear_all：已删除 {deleted_count} 个 Parquet 文件，释放 {total_bytes / 1024 / 1024:.2f} MB")

        # 同时清除同步元数据
        from .sync_manager import _SYNC_META_PARQUET
        from .storage import _get_cache_root
        sync_meta_file = _get_cache_root() / _SYNC_META_PARQUET
        if sync_meta_file.exists():
            sync_meta_file.unlink()
            logger.info("clear_all：已清除同步元数据文件")

        result["success"] = True
        result["deleted_files"] = deleted_count
        result["freed_mb"] = round(total_bytes / (1024 * 1024), 2)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"clear_all 失败：{e}", exc_info=True)

    return result


def clear_symbol(symbol: str, period: Optional[str] = None) -> Dict:
    """
    清除指定股票的缓存（可指定周期，不指定则清除所有周期）。

    Args:
        symbol: 股票代码
        period: 数据周期，None 表示清除该股票所有周期的缓存

    Returns:
        字典，包含 success、deleted_files、freed_mb、error
    """
    storage = get_default_storage()
    result = {
        "success": False,
        "deleted_files": 0,
        "freed_mb": 0.0,
        "error": None,
    }

    try:
        total_bytes = 0
        deleted_count = 0

        if period:
            # 删除指定周期
            file_path = storage._get_file_path(symbol, period)
            if file_path.exists():
                total_bytes += file_path.stat().st_size
                file_path.unlink()
                deleted_count += 1
        else:
            # 删除所有周期
            for p in storage.list_periods():
                file_path = storage._get_file_path(symbol, p)
                if file_path.exists():
                    total_bytes += file_path.stat().st_size
                    file_path.unlink()
                    deleted_count += 1

        result["success"] = True
        result["deleted_files"] = deleted_count
        result["freed_mb"] = round(total_bytes / (1024 * 1024), 4)
        logger.info(f"clear_symbol：{symbol} {period or '全部周期'}，删除 {deleted_count} 个文件")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"clear_symbol 失败：{symbol}，错误：{e}", exc_info=True)

    return result


# ------------------------------------------------------------------
# 板块层次关系映射（本地硬编码 + 动态推断）
# ------------------------------------------------------------------

# 市场分类板块的硬编码父子关系映射
# key = 子板块名称，value = 父板块名称（None 表示顶层）
_MARKET_SECTOR_PARENT_MAP: Dict[str, Optional[str]] = {
    # ── 顶层市场分类（parent = None）──────────────────────────
    "沪深京A股": None,
    "沪深A股":   "沪深京A股",   # 沪深A股 归属于 沪深京A股
    "沪深B股":   None,
    "沪深ETF":   None,
    "沪深指数":  None,
    "沪深基金":  None,
    "沪深债券":  None,
    "沪深转债":  None,
    "香港联交所股票": None,
    "连续合约":  None,
    # ── 交易所分类（parent = 对应沪深板块）────────────────────
    "上证A股":   "沪深A股",
    "深证A股":   "沪深A股",
    "京市A股":   "沪深京A股",   # 京市A股 直接归属于 沪深京A股
    "上证B股":   "沪深B股",
    "深证B股":   "沪深B股",
    "沪市ETF":   "沪深ETF",
    "深市ETF":   "沪深ETF",
    "沪市指数":  "沪深指数",
    "深市指数":  "沪深指数",
    "沪市基金":  "沪深基金",
    "深市基金":  "沪深基金",
    "沪市债券":  "沪深债券",
    "深市债券":  "沪深债券",
    "上证转债":  "沪深转债",
    "深证转债":  "沪深转债",
    # ── 板块细分（parent = 对应交易所板块）────────────────────
    "创业板":    "深证A股",
    "科创板":    "上证A股",
    "科创板CDR": "上证A股",
    # ── 期货交易所（归属于虚拟顶层节点"期货"）────────────────────────────────
    "上期所":    "期货",
    "大商所":    "期货",
    "郑商所":    "期货",
    "中金所":    "期货",
}


def _build_sector_parent_map(sectors_data: List[Dict]) -> Dict[str, Optional[str]]:
    """
    构建板块父子关系映射表。

    策略：
    1. 市场分类板块（沪深A股、上证A股 等）：使用硬编码映射表
    2. 申万行业（SW 前缀）：
       - SW1xxx 为顶层（parent=None）
       - SW2xxx 的父级 = 成分股集合包含该 SW2 所有成分股的 SW1
       - SW3xxx 的父级 = 成分股集合包含该 SW3 所有成分股的 SW2
       - 加权板块（xxx加权）的父级 = 对应的非加权板块
    3. 证监会行业（CSRC 前缀）：
       - CSRC1xxx 为顶层（parent=None）
       - CSRC2xxx 的父级 = 成分股集合包含该 CSRC2 所有成分股的 CSRC1

    Args:
        sectors_data: 已读取的板块数据列表，每项含 name 和 _stocks（成分股集合，内部字段）

    Returns:
        dict，key=板块名称，value=父板块名称（None 表示顶层）
    """
    parent_map: Dict[str, Optional[str]] = {}

    # 按名称建立索引
    stocks_by_name: Dict[str, set] = {
        s["name"]: s.get("_stocks", set()) for s in sectors_data
    }

    for sector in sectors_data:
        name = sector["name"]

        # ── 市场分类：直接查硬编码映射 ──────────────────────────
        if name in _MARKET_SECTOR_PARENT_MAP:
            parent_map[name] = _MARKET_SECTOR_PARENT_MAP[name]
            continue

        # ── 加权板块：跳过，不建立父子关系（已在统计阶段过滤）────────
        if name.endswith("加权"):
            continue

        # ── 申万行业 SW ──────────────────────────────────────────
        if name.startswith("SW1"):
            parent_map[name] = "申万行业"  # 一级归属于虚拟顶层节点
        elif name.startswith("SW2"):
            # 找包含该 SW2 所有成分股的 SW1
            my_stocks = stocks_by_name.get(name, set())
            best_parent = _find_parent_by_stocks(
                my_stocks, stocks_by_name, prefix="SW1", exclude_suffix="加权"
            )
            parent_map[name] = best_parent
        elif name.startswith("SW3"):
            # 找包含该 SW3 所有成分股的 SW2
            my_stocks = stocks_by_name.get(name, set())
            best_parent = _find_parent_by_stocks(
                my_stocks, stocks_by_name, prefix="SW2", exclude_suffix="加权"
            )
            parent_map[name] = best_parent

        # ── 证监会行业 CSRC ──────────────────────────────────────
        elif name.startswith("CSRC1"):
            parent_map[name] = "证监会行业"  # 一级归属于虚拟顶层节点
        elif name.startswith("CSRC2"):
            my_stocks = stocks_by_name.get(name, set())
            best_parent = _find_parent_by_stocks(
                my_stocks, stocks_by_name, prefix="CSRC1", exclude_suffix="加权"
            )
            parent_map[name] = best_parent

        else:
            # 未匹配任何规则的板块，置为顶层
            parent_map[name] = None

    # ── 注入虚拟节点（SW/CSRC/期货 的聚合根，以及 SW加权 汇总节点）──
    # 仅当实际存在对应子节点时才注入，避免空节点出现
    has_sw      = any(n.startswith("SW")   for n in parent_map)
    has_csrc    = any(n.startswith("CSRC") for n in parent_map)
    has_futures = any(parent_map.get(n) == "期货" for n in parent_map)
    if has_sw:
        parent_map["申万行业"]   = None  # 虚拟顶层，无父级
    if has_csrc:
        parent_map["证监会行业"] = None  # 虚拟顶层，无父级
    if has_futures:
        parent_map["期货"]       = None  # 虚拟顶层，无父级

    return parent_map


def _find_parent_by_stocks(
    my_stocks: set,
    stocks_by_name: Dict[str, set],
    prefix: str,
    exclude_suffix: str = "",
) -> Optional[str]:
    """
    通过成分股包含关系找父板块。

    找所有以 prefix 开头（且不以 exclude_suffix 结尾）的候选父板块，
    选出包含 my_stocks 所有成分股、且自身成分股数量最少的那个（最精确的父级）。

    Args:
        my_stocks:       当前板块的成分股集合
        stocks_by_name:  所有板块的成分股字典
        prefix:          候选父板块的名称前缀
        exclude_suffix:  排除以此后缀结尾的候选父板块

    Returns:
        父板块名称，找不到时返回 None
    """
    if not my_stocks:
        return None

    best_parent: Optional[str] = None
    best_size = float("inf")

    for candidate_name, candidate_stocks in stocks_by_name.items():
        if not candidate_name.startswith(prefix):
            continue
        if exclude_suffix and candidate_name.endswith(exclude_suffix):
            continue
        if not candidate_stocks:
            continue
        # 候选父板块必须包含当前板块的所有成分股
        if my_stocks.issubset(candidate_stocks):
            # 选成分股数量最少的（最精确的父级）
            if len(candidate_stocks) < best_size:
                best_size = len(candidate_stocks)
                best_parent = candidate_name

    return best_parent


# A 股开市日，早于此日期的数据均为脏数据
_ASHARE_OPEN_DATE = "1990-12-19"


def clear_date_anomaly(symbol: str, period: str) -> Dict:
    """
    精准行级清理：删除指定股票缓存中早于 A 股开市日（1990-12-19）的脏数据行。

    仅删除异常行，保留正常数据，并将清理后的数据回写到原文件。
    回写时保持原有 schema（列名、类型、DatetimeIndex）不变。

    Args:
        symbol: 股票代码，如 '600000.SH'
        period: 数据周期，如 '1d'

    Returns:
        字典，包含：
          - success:      是否成功（bool）
          - removed_rows: 删除的异常行数（int）
          - freed_mb:     释放的磁盘空间（MB，清理前后文件大小差值）
          - error:        错误信息（str 或 None）
    """
    storage = get_default_storage()
    file_path = storage._get_file_path(symbol, period)

    result: Dict = {
        "success": False,
        "removed_rows": 0,
        "freed_mb": 0.0,
        "error": None,
    }

    if not file_path.exists():
        result["success"] = True  # 文件不存在，视为无需清理
        return result

    try:
        df = pd.read_parquet(file_path, engine="pyarrow")

        if df.empty:
            result["success"] = True
            return result

        # 确保索引是 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # 找出早于 A 股开市日的异常行
        threshold = pd.Timestamp(_ASHARE_OPEN_DATE)
        anomaly_mask = df.index < threshold
        removed_rows = int(anomaly_mask.sum())

        if removed_rows == 0:
            result["success"] = True
            return result

        # 记录清理前文件大小
        size_before = file_path.stat().st_size

        # 过滤掉异常行，保留正常数据
        df_clean = df[~anomaly_mask]

        # 回写到原文件，保持 schema 不变
        df_clean.to_parquet(file_path, engine="pyarrow")

        # 计算释放空间
        size_after = file_path.stat().st_size if file_path.exists() else 0
        freed_bytes = max(0, size_before - size_after)

        result["success"] = True
        result["removed_rows"] = removed_rows
        result["freed_mb"] = round(freed_bytes / (1024 * 1024), 4)
        logger.info(
            f"clear_date_anomaly：{symbol} {period}，"
            f"删除 {removed_rows} 行异常数据，释放 {result['freed_mb']:.4f} MB"
        )

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"clear_date_anomaly 失败：{symbol} {period}，错误：{e}", exc_info=True)

    return result


def batch_clear_date_anomaly(
    symbol_list: List[str],
    period: str,
    on_progress: Optional[callable] = None,
    stop_flag: Optional[callable] = None,
) -> Dict:
    """
    批量精准行级清理：对股票列表中所有存在日期异常的缓存执行行级清理。

    Args:
        symbol_list:  股票代码列表
        period:       数据周期，如 '1d'
        on_progress:  进度回调 (done: int, total: int)
        stop_flag:    停止检查函数，返回 True 时停止

    Returns:
        字典，包含：
          - success:            整体是否成功（未中断且无异常）
          - total:              扫描总数
          - anomaly_found:      发现异常的股票数
          - cleaned:            成功清理的股票数
          - failed:             清理失败的股票数
          - total_removed_rows: 共删除的异常行数
          - freed_mb:           共释放的磁盘空间（MB）
          - interrupted:        是否被 stop_flag 中断
          - errors:             失败详情列表 [{'symbol': str, 'error': str}, ...]
    """
    total = len(symbol_list)
    result: Dict = {
        "success": False,
        "total": total,
        "anomaly_found": 0,
        "cleaned": 0,
        "failed": 0,
        "total_removed_rows": 0,
        "freed_mb": 0.0,
        "interrupted": False,
        "errors": [],
    }

    for idx, symbol in enumerate(symbol_list):
        if stop_flag and stop_flag():
            result["interrupted"] = True
            break

        r = clear_date_anomaly(symbol, period)

        if not r["success"]:
            result["failed"] += 1
            result["errors"].append({"symbol": symbol, "error": r.get("error", "未知错误")})
        elif r["removed_rows"] > 0:
            result["anomaly_found"] += 1
            result["cleaned"] += 1
            result["total_removed_rows"] += r["removed_rows"]
            result["freed_mb"] += r["freed_mb"]

        if on_progress:
            on_progress(idx + 1, total)

    result["freed_mb"] = round(result["freed_mb"], 4)
    result["success"] = not result["interrupted"] and result["failed"] == 0
    logger.info(
        f"batch_clear_date_anomaly 完成：扫描 {total}，"
        f"发现异常 {result['anomaly_found']}，"
        f"成功清理 {result['cleaned']}，"
        f"失败 {result['failed']}，"
        f"共删除 {result['total_removed_rows']} 行"
    )
    return result


def batch_delete_no_open_date(
    symbol_list: List[str],
    period: Optional[str] = None,
    on_progress: Optional[callable] = None,
    stop_flag: Optional[callable] = None,
) -> Dict:
    """
    批量整个文件删除：删除指定股票列表的 Parquet 缓存文件。

    与 batch_clear_date_anomaly（行级清理）不同，此函数直接删除整个文件，
    适用于上市日期缺失等需要完整重新同步的场景。

    Args:
        symbol_list:  股票代码列表
        period:       数据周期，None 表示删除所有周期
        on_progress:  进度回调 (done: int, total: int)
        stop_flag:    停止检查函数，返回 True 时停止

    Returns:
        字典，包含：
          - success:      整体是否成功（未中断且无失败）
          - total:        处理总数
          - deleted:      成功删除的股票数（至少删除了一个文件）
          - failed:       删除失败的股票数
          - freed_mb:     共释放的磁盘空间（MB）
          - interrupted:  是否被 stop_flag 中断
          - errors:       失败详情列表 [{'symbol': str, 'error': str}, ...]
    """
    total = len(symbol_list)
    result: Dict = {
        "success": False,
        "total": total,
        "deleted": 0,
        "failed": 0,
        "freed_mb": 0.0,
        "interrupted": False,
        "errors": [],
    }

    for idx, symbol in enumerate(symbol_list):
        if stop_flag and stop_flag():
            result["interrupted"] = True
            break

        r = clear_symbol(symbol, period)

        if not r["success"]:
            result["failed"] += 1
            result["errors"].append({"symbol": symbol, "error": r.get("error", "未知错误")})
        elif r["deleted_files"] > 0:
            result["deleted"] += 1
            result["freed_mb"] += r["freed_mb"]

        if on_progress:
            on_progress(idx + 1, total)

    result["freed_mb"] = round(result["freed_mb"], 4)
    result["success"] = not result["interrupted"] and result["failed"] == 0
    logger.info(
        f"batch_delete_no_open_date 完成：处理 {total}，"
        f"成功删除 {result['deleted']}，"
        f"失败 {result['failed']}，"
        f"释放 {result['freed_mb']:.4f} MB"
    )
    return result
