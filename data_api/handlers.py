# -*- coding: utf-8 -*-
"""
data_api/handlers.py — 所有路由的业务处理逻辑

路由列表：
  GET /health                  — 健康检查
  GET /api/v1/kline            — K 线数据查询
  GET /api/v1/sector           — 板块成分股查询
  GET /api/v1/instruments      — 合约基础信息查询
  GET /api/v1/calendar         — 交易日历查询

数据访问原则：
  所有数据读取必须通过 DataService 的现有方法，禁止直接读取 Parquet 文件绕过服务层。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from data_api.server import ok_response, err_response, API_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()

# 缓存根目录
_CACHE_ROOT = Path.home() / ".qmtquant" / "cache"

# 合约信息 Parquet 路径（相对于缓存根目录）
_INSTRUMENT_PARQUET = _CACHE_ROOT / "stock" / "instrument" / "instrument_detail.parquet"
# 交易日历 Parquet 路径
_CALENDAR_PARQUET = _CACHE_ROOT / "stock" / "calendar" / "trading_calendar.parquet"


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def _count_parquet_files(directory: Path) -> int:
    """递归统计目录下的 .parquet 文件数量"""
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.rglob("*.parquet"))


def _get_data_service():
    """获取 DataService 单例（延迟导入，避免循环依赖）"""
    from data_manager.data_service import DataService
    return DataService()


def _parse_date_param(date_str: Optional[str]) -> Optional[str]:
    """
    将日期参数统一转换为 'YYYYMMDD' 格式（DataService.query_kline 接受的格式）。
    支持输入：'20240101' 或 '2024-01-01'
    """
    if not date_str:
        return None
    return date_str.replace("-", "")


# ──────────────────────────────────────────────────────────────────
# 需求 6：健康检查接口
# ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """
    健康检查接口。

    返回服务状态、版本号、缓存目录路径及各数据目录文件数量统计。
    """
    cache_stats = {
        "stock_kline_1d": _count_parquet_files(_CACHE_ROOT / "stock" / "kline" / "1d"),
        "stock_kline_1m": _count_parquet_files(_CACHE_ROOT / "stock" / "kline" / "1m"),
        "stock_instrument": _count_parquet_files(_CACHE_ROOT / "stock" / "instrument"),
        "stock_calendar": _count_parquet_files(_CACHE_ROOT / "stock" / "calendar"),
        "industry_members": _count_parquet_files(_CACHE_ROOT / "industry" / "members"),
        "industry_sector_list": _count_parquet_files(_CACHE_ROOT / "industry" / "sector_list"),
    }
    return ok_response(data={
        "status": "ok",
        "version": API_VERSION,
        "cache_root": str(_CACHE_ROOT),
        "cache_stats": cache_stats,
    })


# ──────────────────────────────────────────────────────────────────
# 需求 2：K 线数据查询接口
# ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/kline")
async def get_kline(
    symbol: str = Query(..., description="股票代码，如 600519.SH"),
    period: str = Query("1d", description="数据周期，如 1d、1m"),
    start: Optional[str] = Query(None, description="起始日期，格式 YYYYMMDD 或 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期，格式 YYYYMMDD 或 YYYY-MM-DD"),
    format: str = Query("standard", description="返回格式：standard（默认，STANDARD_COLUMNS）或 raw（原始字段）"),
):
    """
    K 线数据查询接口。

    - format=standard（默认）：返回 date/open/high/low/close/volume/amount/pct_chg
    - format=raw：返回 Parquet 原始字段，不做任何转换
    """
    try:
        ds = _get_data_service()
        start_date = _parse_date_param(start)
        end_date = _parse_date_param(end)

        df = ds.query_kline(symbol, period, start_date, end_date)

        if df is None or df.empty:
            return ok_response(data=[], message=f"暂无数据：{symbol} {period}")

        if format == "raw":
            # 原始字段：将 DatetimeIndex 转为字符串，NaN 转为 None
            df_reset = df.reset_index()
            # 将 DatetimeIndex 列（通常名为 index 或 date）转为字符串
            if df_reset.columns[0] in ("index", "date"):
                df_reset.rename(columns={df_reset.columns[0]: "date"}, inplace=True)
                df_reset["date"] = df_reset["date"].dt.strftime("%Y-%m-%d")
            records = df_reset.where(df_reset.notna(), other=None).to_dict(orient="records")
            return ok_response(data=records)

        # format=standard：转换为 STANDARD_COLUMNS 格式
        records = _to_standard_format(df, symbol)
        return ok_response(data=records)

    except Exception as e:
        logger.error(f"get_kline 失败 [{symbol} {period}]: {e}", exc_info=True)
        return err_response(f"查询失败：{type(e).__name__}: {str(e)[:200]}", code=500, status_code=500)


def _to_standard_format(df, symbol: str) -> list:
    """
    将 DataService.query_kline() 返回的 DataFrame 转换为 STANDARD_COLUMNS 格式。

    STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']

    pct_chg 计算规则：
      - 优先使用 preClose 字段：(close - preClose) / preClose * 100
      - preClose 缺失或为 0 时，用相邻行 close 计算
      - 结果保留两位小数
    """
    import pandas as pd

    result = []
    df = df.copy()

    # 确保索引为 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        logger.warning(f"[{symbol}] DataFrame 索引不是 DatetimeIndex，尝试转换")
        df.index = pd.to_datetime(df.index)

    # 计算 pct_chg
    if "preClose" in df.columns:
        pre_close = df["preClose"].astype(float)
        close = df["close"].astype(float)
        # preClose 为 0 或 NaN 时用 shift(1) 兜底
        valid_mask = pre_close.notna() & (pre_close != 0)
        pct_chg = pd.Series(index=df.index, dtype=float)
        pct_chg[valid_mask] = (close[valid_mask] - pre_close[valid_mask]) / pre_close[valid_mask] * 100
        # 无效行用 close.pct_change() 兜底
        pct_chg[~valid_mask] = close.pct_change()[~valid_mask] * 100
    else:
        pct_chg = df["close"].astype(float).pct_change() * 100

    for i, (idx, row) in enumerate(df.iterrows()):
        def _safe(val):
            """将 NaN/inf 转为 None"""
            try:
                if val is None:
                    return None
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return None
                return f
            except (TypeError, ValueError):
                return None

        def _round(val, ndigits):
            """安全 round，None/NaN/inf 返回 None"""
            v = _safe(val)
            return round(v, ndigits) if v is not None else None

        record = {
            "date": idx.strftime("%Y-%m-%d"),
            "open":   _round(row.get("open"),   4),
            "high":   _round(row.get("high"),   4),
            "low":    _round(row.get("low"),    4),
            "close":  _round(row.get("close"),  4),
            "volume": _safe(row.get("volume")),
            "amount": _round(row.get("amount"), 2),
            "pct_chg": round(float(pct_chg.iloc[i]), 2) if _safe(pct_chg.iloc[i]) is not None else None,
        }
        result.append(record)

    return result


# ──────────────────────────────────────────────────────────────────
# 需求 3：板块成分股查询接口
# ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/sector")
async def get_sector(
    name: Optional[str] = Query(None, description="板块名称，如 沪深300；不传则返回所有板块名称列表"),
):
    """
    板块成分股查询接口。

    - 不带 name 参数：返回所有可用板块名称列表
    - 带 name 参数：返回该板块的成分股列表 [{symbol, name}, ...]
    """
    try:
        if name is None:
            # 返回所有板块名称列表
            return _get_all_sectors()

        # 返回指定板块的成分股
        ds = _get_data_service()
        members = ds.get_sector(name)

        if not members:
            return ok_response(data=[], message=f"板块 '{name}' 暂无数据或不存在")

        # members 格式：[[symbol, sector_name], ...]
        # 转换为 [{symbol, name}, ...] 格式
        result = []
        for item in members:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                result.append({
                    "symbol": item[0],
                    "name": item[1] if len(item) > 1 else "",
                })
            elif isinstance(item, str):
                result.append({"symbol": item, "name": ""})

        return ok_response(data=result)

    except Exception as e:
        logger.error(f"get_sector 失败 [name={name}]: {e}", exc_info=True)
        return err_response(f"查询失败：{type(e).__name__}: {str(e)[:200]}", code=500, status_code=500)


def _get_all_sectors() -> JSONResponse:
    """读取 sector_list.parquet，返回所有板块名称列表"""
    import pandas as pd

    sector_list_path = _CACHE_ROOT / "industry" / "sector_list" / "sector_list.parquet"
    if not sector_list_path.exists():
        return ok_response(data=[], message="板块列表文件不存在，请先执行 sync --asset industry")

    try:
        df = pd.read_parquet(sector_list_path)
        if df.empty or "sector_name" not in df.columns:
            return ok_response(data=[], message="板块列表为空")
        sectors = df["sector_name"].tolist()
        return ok_response(data=sectors)
    except Exception as e:
        logger.error(f"读取 sector_list 失败: {e}", exc_info=True)
        return err_response(f"读取板块列表失败：{str(e)[:200]}", code=500, status_code=500)


# ──────────────────────────────────────────────────────────────────
# 需求 4：合约基础信息查询接口
# ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/instruments")
async def get_instruments(
    symbols: Optional[str] = Query(None, description="股票代码，多个用英文逗号分隔，如 600519.SH,000001.SZ；不传则返回全量（分页）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(500, ge=1, le=5000, description="每页数量，默认 500"),
):
    """
    合约基础信息查询接口。

    - 不带 symbols：返回全量合约信息（分页）
    - 带 symbols：返回指定股票的合约信息
    """
    if not _INSTRUMENT_PARQUET.exists():
        return err_response(
            "合约信息文件不存在，请先执行：python dm_cli.py sync --asset stock --sub instrument",
            code=503,
            status_code=503,
        )

    try:
        from data_manager.aux_data import load_instrument_detail

        detail_dict = load_instrument_detail()
        if not detail_dict:
            return ok_response(data=[], message="合约信息为空")

        if symbols:
            # 批量查询指定 symbols
            symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
            result = []
            for sym in symbol_list:
                if sym in detail_dict:
                    item = {"symbol": sym}
                    item.update(_sanitize_instrument(detail_dict[sym]))
                    result.append(item)
                # 不存在的 symbol 直接跳过（需求 4.3）
            return ok_response(data=result)
        else:
            # 全量分页返回
            all_items = []
            for sym, info in detail_dict.items():
                item = {"symbol": sym}
                item.update(_sanitize_instrument(info))
                all_items.append(item)

            total = len(all_items)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_data = all_items[start_idx:end_idx]

            return ok_response(data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total > 0 else 0,
                "items": page_data,
            })

    except Exception as e:
        logger.error(f"get_instruments 失败: {e}", exc_info=True)
        return err_response(f"查询失败：{type(e).__name__}: {str(e)[:200]}", code=500, status_code=500)


def _sanitize_instrument(info: dict) -> dict:
    """将合约信息中的特殊值（NaN/inf/None）转为 JSON 安全的格式"""
    result = {}
    for k, v in info.items():
        if v is None:
            result[k] = None
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                result[k] = None
            else:
                result[k] = v
        elif hasattr(v, 'item'):
            # numpy 标量转 Python 原生类型
            try:
                result[k] = v.item()
            except Exception:
                result[k] = str(v)
        else:
            result[k] = v
    return result


# ──────────────────────────────────────────────────────────────────
# 需求 5：交易日历查询接口
# ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/calendar")
async def get_calendar(
    start: Optional[str] = Query(None, description="起始日期，格式 YYYYMMDD 或 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期，格式 YYYYMMDD 或 YYYY-MM-DD"),
):
    """
    交易日历查询接口。

    返回 YYYY-MM-DD 格式的交易日列表。
    """
    if not _CALENDAR_PARQUET.exists():
        return err_response(
            "交易日历文件不存在，请先执行：python dm_cli.py sync --asset stock --sub calendar",
            code=503,
            status_code=503,
        )

    try:
        from data_manager.aux_data import load_trading_calendar

        dates = load_trading_calendar()
        if not dates:
            return ok_response(data=[], message="交易日历为空")

        # 过滤日期范围
        if start or end:
            # 统一转为 YYYY-MM-DD 格式进行比较
            start_norm = _normalize_date_for_compare(start)
            end_norm = _normalize_date_for_compare(end)

            filtered = []
            for d in dates:
                # dates 元素格式为 'YYYY-MM-DD'
                if start_norm and d < start_norm:
                    continue
                if end_norm and d > end_norm:
                    continue
                filtered.append(d)
            dates = filtered

        return ok_response(data=dates)

    except Exception as e:
        logger.error(f"get_calendar 失败: {e}", exc_info=True)
        return err_response(f"查询失败：{type(e).__name__}: {str(e)[:200]}", code=500, status_code=500)


def _normalize_date_for_compare(date_str: Optional[str]) -> Optional[str]:
    """
    将日期字符串统一转为 'YYYY-MM-DD' 格式，用于与交易日历列表比较。
    支持输入：'20240101' 或 '2024-01-01'
    """
    if not date_str:
        return None
    s = date_str.strip().replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return date_str  # 已是 YYYY-MM-DD 格式
