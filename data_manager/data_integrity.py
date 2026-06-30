# -*- coding: utf-8 -*-
"""
data_manager/data_integrity.py — 数据完整性检测

提供以下功能：
  1. 从 Parquet 缓存读取某只股票某周期的已有交易日期集合
  2. 与交易日历对比，计算缺口段（连续缺失的交易日区间）
  3. 批量扫描股票池，返回所有缺口信息

设计原则：
- 纯 Python，独立可运行
  - 直接读取 Parquet 文件索引，不依赖 sync_meta.json（可能有历史脏数据）
  - 日期格式统一使用 'YYYY-MM-DD' 字符串进行集合比较
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from .storage import get_default_storage

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 核心工具函数
# ------------------------------------------------------------------

def get_cached_dates(symbol: str, period: str) -> Set[str]:
    """
    从 Parquet 缓存读取指定股票/周期的已有交易日期集合。

    直接扫描文件索引，不依赖 sync_meta.json。
    返回格式统一为 'YYYY-MM-DD' 字符串集合。

    Args:
        symbol: 股票代码，如 '600000.SH'
        period: 数据周期，如 '1d'

    Returns:
        已有日期集合（'YYYY-MM-DD' 格式），若文件不存在则返回空集合
    """
    storage = get_default_storage()
    file_path = storage._get_file_path(symbol, period)

    if not file_path.exists():
        return set()

    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
        if df.empty:
            return set()

        # 确保索引是 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # 过滤无效日期（NaT）
        valid_idx = df.index[df.index.notna()]

        # 统一转为 'YYYY-MM-DD' 字符串
        return {str(ts.date()) for ts in valid_idx}

    except Exception as e:
        logger.error(f"get_cached_dates 失败 [{symbol} {period}]：{e}", exc_info=True)
        return set()


def get_date_range(symbol: str, period: str) -> Tuple[Optional[str], Optional[str]]:
    """
    获取 Parquet 缓存中某只股票/周期的数据日期范围。

    直接读取文件索引，不依赖 sync_meta.json。

    Returns:
        (start_date, end_date)，格式 'YYYY-MM-DD'；文件不存在时返回 (None, None)
    """
    storage = get_default_storage()
    file_path = storage._get_file_path(symbol, period)

    if not file_path.exists():
        return None, None

    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
        if df.empty:
            return None, None

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        valid_idx = df.index[df.index.notna()]
        if valid_idx.empty:
            return None, None

        return str(valid_idx.min().date()), str(valid_idx.max().date())

    except Exception as e:
        logger.error(f"get_date_range 失败 [{symbol} {period}]：{e}", exc_info=True)
        return None, None


def calc_gap_segments(
    actual_dates: Set[str],
    trading_dates_sorted: List[str],
    range_start: str,
    range_end: str,
) -> List[Tuple[str, str]]:
    """
    计算缺口段列表。

    在 [range_start, range_end] 区间内，找出交易日历中存在但
    actual_dates 中缺失的日期，并将连续缺失的交易日合并为段。

    注意：两边日期格式必须统一为 'YYYY-MM-DD'，否则集合比较会产生假缺失。

    Args:
        actual_dates:          实际已有 bar 的日期集合（'YYYY-MM-DD' 格式）
        trading_dates_sorted:  已排序的交易日历列表（'YYYY-MM-DD' 格式）
        range_start:           区间起始日期（'YYYY-MM-DD'，含）
        range_end:             区间结束日期（'YYYY-MM-DD'，含）

    Returns:
        list[tuple[str, str]]  每个元素为 (gap_start, gap_end)，格式 'YYYYMMDD'
    """
    # 筛选出区间内的缺失交易日
    missing = [
        d for d in trading_dates_sorted
        if range_start <= d <= range_end and d not in actual_dates
    ]
    if not missing:
        return []

    # 建立交易日索引，用于判断相邻关系
    td_index = {d: i for i, d in enumerate(trading_dates_sorted)}

    segments: List[Tuple[str, str]] = []
    seg_start = missing[0]
    seg_prev = missing[0]

    for d in missing[1:]:
        # 若当前日期与上一个缺失日期在交易日历中相邻，则属于同一段
        if td_index.get(d, -1) == td_index.get(seg_prev, -2) + 1:
            seg_prev = d
        else:
            segments.append((
                seg_start.replace("-", ""),
                seg_prev.replace("-", ""),
            ))
            seg_start = d
            seg_prev = d

    segments.append((
        seg_start.replace("-", ""),
        seg_prev.replace("-", ""),
    ))
    return segments


def scan_symbol_gaps(
    symbol: str,
    period: str,
    trading_dates_sorted: List[str],
    range_end: Optional[str] = None,
) -> Dict:
    """
    扫描单只股票的数据缺口。

    Args:
        symbol:                股票代码
        period:                数据周期
        trading_dates_sorted:  已排序的交易日历（'YYYY-MM-DD' 格式）
        range_end:             扫描截止日期（'YYYY-MM-DD'），None 表示今天

    Returns:
        字典，包含：
          - symbol:       股票代码
          - period:       数据周期
          - has_cache:    是否有本地缓存（bool）
          - range_start:  缓存数据起始日期（str 或 None）
          - range_end:    扫描截止日期（str）
          - gap_count:    缺口段数量
          - segments:     缺口段列表 [(start_yyyymmdd, end_yyyymmdd), ...]
    """
    if range_end is None:
        range_end = datetime.now().strftime("%Y-%m-%d")

    actual_dates = get_cached_dates(symbol, period)
    range_start, _ = get_date_range(symbol, period)

    result = {
        "symbol": symbol,
        "period": period,
        "has_cache": bool(actual_dates),
        "range_start": range_start,
        "range_end": range_end,
        "gap_count": 0,
        "segments": [],
    }

    if not actual_dates or not range_start:
        # 无缓存，整个区间都是缺口（但不在此函数中处理，由调用方决定策略）
        return result

    segments = calc_gap_segments(
        actual_dates, trading_dates_sorted, range_start, range_end
    )
    result["gap_count"] = len(segments)
    result["segments"] = segments
    return result


def batch_scan_gaps(
    symbol_list: List[str],
    period: str,
    trading_dates_sorted: List[str],
    range_end: Optional[str] = None,
    on_progress: Optional[callable] = None,
    stop_flag: Optional[callable] = None,
) -> Dict[str, Dict]:
    """
    批量扫描股票池的数据缺口。

    Args:
        symbol_list:           股票代码列表
        period:                数据周期
        trading_dates_sorted:  已排序的交易日历（'YYYY-MM-DD' 格式）
        range_end:             扫描截止日期，None 表示今天
        on_progress:           进度回调 (done: int, total: int)
        stop_flag:             停止检查函数，返回 True 时停止

    Returns:
        {symbol: scan_result_dict}
    """
    if range_end is None:
        range_end = datetime.now().strftime("%Y-%m-%d")

    total = len(symbol_list)
    results: Dict[str, Dict] = {}

    for idx, symbol in enumerate(symbol_list):
        if stop_flag and stop_flag():
            break

        results[symbol] = scan_symbol_gaps(
            symbol, period, trading_dates_sorted, range_end
        )

        if on_progress:
            on_progress(idx + 1, total)

    return results


# ------------------------------------------------------------------
# 全面健康检查（validate）
# ------------------------------------------------------------------

def _check_field_type(series: "pd.Series", type_tag: str) -> bool:
    """
    检查 pandas Series 是否符合指定的类型标识。

    type_tag 支持：
      'numeric'   - float 或 int（含 pandas float64/int64 等）
      'date'      - datetime64[ns]（时间部分为 00:00:00）或 object 列中存储 'YYYY-MM-DD' 字符串
      'datetime'  - datetime64[ns]（含时分秒）
      'timestamp' - int64（毫秒或秒级整数时间戳）
      'string'    - object 或 StringDtype
    """
    import pandas as pd

    dtype = series.dtype
    if type_tag == 'numeric':
        return pd.api.types.is_numeric_dtype(dtype)
    elif type_tag == 'date':
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return True
        # object 列：检查非空样本是否符合 'YYYY-MM-DD' 格式
        if dtype == object:
            sample = series.dropna().head(5)
            if sample.empty:
                return True
            import re
            pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
            return all(isinstance(v, str) and pattern.match(v) for v in sample)
        return False
    elif type_tag == 'datetime':
        return pd.api.types.is_datetime64_any_dtype(dtype)
    elif type_tag == 'timestamp':
        return pd.api.types.is_integer_dtype(dtype)
    elif type_tag == 'string':
        return dtype == object or str(dtype) == 'string'
    return False


def validate_symbol(
    symbol: str,
    period: str,
    sub_type_config,
    trading_dates_sorted: List[str],
    instrument_df: Optional["pd.DataFrame"] = None,
) -> Dict:
    """
    对单只股票执行全面健康检查。

    检测维度：
      1. 字段完整度：required_fields 是否全部存在
      2. 字段类型一致性：field_types 中各列是否符合期望类型；索引是否为 DatetimeIndex
      3. 前缺失：T1（= max(open_date, 交易日历最早日期)）到 cache_start 之间的缺失
      4. 后缺失：cache_end 到 T2（= min(expire_date, 最近交易日)）之间的缺失
      5. 中间缺失：cache_start ~ cache_end 范围内 bar 与交易日历不对应的段

    T1/T2 定义：
      T1 = max(open_date, CALENDAR_START)  — 前缺失起点（以交易日历最早日期为基线）
      T2 = min(expire_date, 最近交易日)    — 后缺失终点（退市股票不超过退市日）

    Args:
        symbol:               股票代码，如 '600000.SH'
        period:               数据周期，如 '1d'
        sub_type_config:      SubTypeConfig 实例（含 required_fields / field_types）
        trading_dates_sorted: 已排序的交易日历列表（'YYYY-MM-DD' 格式）
        instrument_df:        合约信息 DataFrame（索引为 symbol），None 时跳过前缺失检测

    Returns:
        字典，包含：
          symbol, has_cache, field_ok, type_ok,
          missing_fields, type_errors,
          head_missing, tail_missing,
          cache_start, cache_end, open_date,
          gap_segments, head_gap_segments, tail_start,
          date_anomaly:     bool       是否存在日期异常（早于 1990-12-19 的脏数据）
          anomaly_count:    int        异常行数
          anomaly_min_date: str|None   最早异常日期（'YYYY-MM-DD'）
          no_open_date:     bool       上市日期缺失（合约信息中 open_date 为 None）
          _debug: {
            open_date_raw:        str|None   原始上市日期字符串（YYYYMMDD）
            expire_date_raw:      str|None   原始退市日期字符串（YYYYMMDD），无退市时为 None
            calendar_start:       str|None   交易日历最早日期（'YYYY-MM-DD'）
            latest_trading:       str|None   最近交易日（'YYYY-MM-DD'）
            t1:                   str|None   前缺失起点 = max(open_date, calendar_start)
            t2:                   str|None   后缺失终点 = min(expire_date, latest_trading)
            gap_segment_counts:   list[int]  与 gap_segments 一一对应，每段缺口的交易日数
          }
    """
    import pandas as pd

    result: Dict = {
        'symbol':            symbol,
        'has_cache':         False,
        'field_ok':          True,
        'type_ok':           True,
        'missing_fields':    [],
        'type_errors':       [],   # [{'col': str, 'expected': str, 'actual': str}]
        'head_missing':      0,    # 前缺失交易日数
        'tail_missing':      0,    # 后缺失交易日数
        'cache_start':       None,
        'cache_end':         None,
        'open_date':         None,
    # smart download 所需的缺口段信息
        'gap_segments':      [],   # 缓存范围内的中间缺口段 [(start_yyyymmdd, end_yyyymmdd), ...]
        'head_gap_segments': [],   # T1 到缓存起始之间的缺失段
        'tail_start':        None, # 后缺失的起始补充日期（缓存最新日期的下一个交易日，YYYYMMDD）
        # 日期异常检测：早于 A 股开市日（1990-12-19）的脏数据
        'date_anomaly':      False,
        'anomaly_count':     0,
        'anomaly_min_date':  None,  # 最早异常日期，'YYYY-MM-DD' 格式
        # 上市日期缺失：合约信息中 open_date 为 None，前缺失检测不可信
        'no_open_date':      False,
        # -v 调试字段：T1/T2 推导中间值
        '_debug': {},
    }

    # ── 1. 读取缓存文件 ──────────────────────────────────────────
    storage = get_default_storage()
    file_path = storage._get_file_path(symbol, period)

    if not file_path.exists():
        return result  # has_cache=False，跳过所有检测

    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
    except Exception as e:
        logger.error(f"validate_symbol 读取失败 [{symbol} {period}]：{e}")
        return result  # 不可读，视为无缓存

    if df.empty:
        return result

    result['has_cache'] = True

    # ── 2. 日期异常检测（早于 A 股开市日 1990-12-19 的脏数据）────
    _ASHARE_OPEN_DATE = pd.Timestamp('1990-12-19')
    try:
        _idx = df.index
        if not isinstance(_idx, pd.DatetimeIndex):
            _idx = pd.to_datetime(_idx, errors='coerce')
        if _idx.tz is not None:
            _idx = _idx.tz_localize(None)
        _anomaly_mask = _idx < _ASHARE_OPEN_DATE
        _anomaly_count = int(_anomaly_mask.sum())
        if _anomaly_count > 0:
            result['date_anomaly'] = True
            result['anomaly_count'] = _anomaly_count
            _anomaly_min = _idx[_anomaly_mask].min()
            result['anomaly_min_date'] = str(_anomaly_min.date()) if not pd.isnull(_anomaly_min) else None
    except Exception as _e:
        logger.debug(f"日期异常检测失败 [{symbol} {period}]：{_e}")

    # ── 3. 获取缓存日期范围 ──────────────────────────────────────
    cache_start, cache_end = get_date_range(symbol, period)
    result['cache_start'] = cache_start
    result['cache_end'] = cache_end

    # ── 4. 字段完整度检测 ────────────────────────────────────────
    required = getattr(sub_type_config, 'required_fields', [])
    if required:
        missing = [col for col in required if col not in df.columns]
        if missing:
            result['field_ok'] = False
            result['missing_fields'] = missing

    # ── 5. 字段类型一致性检测 ────────────────────────────────────
    field_types = getattr(sub_type_config, 'field_types', {})

    # 4a. 检查索引是否为 DatetimeIndex（所有子类统一要求）
    if not isinstance(df.index, pd.DatetimeIndex):
        result['type_ok'] = False
        result['type_errors'].append({
            'col':      '__index__',
            'expected': 'DatetimeIndex',
            'actual':   type(df.index).__name__,
        })

    # 4b. 检查各列类型
    if field_types:
        for col, expected_type in field_types.items():
            if col not in df.columns:
                continue  # 缺失列已在字段完整度中报告
            if not _check_field_type(df[col], expected_type):
                result['type_ok'] = False
                result['type_errors'].append({
                    'col':      col,
                    'expected': expected_type,
                    'actual':   str(df[col].dtype),
                })

    # ── 6. 计算 T1 / T2 基线 ─────────────────────────────────────
    # 交易日历最早日期作为全局基线
    calendar_start = trading_dates_sorted[0] if trading_dates_sorted else None

    # 今天字符串
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 最近一个交易日（≤ 今天）
    latest_trading = None
    for d in reversed(trading_dates_sorted):
        if d <= today_str:
            latest_trading = d
            break

    # 解析 open_date / expire_date
    open_date_norm = None    # 'YYYY-MM-DD'
    expire_date_norm = None  # 'YYYY-MM-DD'，None 表示未退市

    if instrument_df is not None:
        try:
            if symbol in instrument_df.index:
                row = instrument_df.loc[symbol]

                # open_date
                raw_open = row.get('open_date') if hasattr(row, 'get') else getattr(row, 'open_date', None)
                open_str = str(raw_open).strip() if raw_open is not None else ''
                if open_str and open_str not in ('0', '99999999', '', 'None', 'nan'):
                    # 过滤 OpenDate 特殊值（197001xx 系列）
                    if not open_str.startswith('1970'):
                        od = open_str.zfill(8)
                        open_date_norm = f"{od[:4]}-{od[4:6]}-{od[6:8]}"

                # expire_date
                raw_expire = row.get('expire_date') if hasattr(row, 'get') else getattr(row, 'expire_date', None)
                try:
                    expire_int = int(float(str(raw_expire))) if raw_expire is not None else 0
                except (ValueError, TypeError):
                    expire_int = 0
                # 0 或 99999999 表示无退市日
                if expire_int not in (0, 99999999) and 19000101 <= expire_int <= 99999998:
                    ed = str(expire_int).zfill(8)
                    expire_date_norm = f"{ed[:4]}-{ed[4:6]}-{ed[6:8]}"
        except Exception as e:
            logger.debug(f"合约信息读取异常 [{symbol}]：{e}")

    result['open_date'] = open_date_norm.replace('-', '') if open_date_norm else None

    # 上市日期缺失检测：open_date 为 None 时标记，并跳过前缺失检测
    if open_date_norm is None and result['has_cache']:
        result['no_open_date'] = True

    # T1 = max(open_date, calendar_start)
    # 注意：open_date 为 None 时不 fallback 到 calendar_start，直接置 t1=None 跳过前缺失
    t1 = None
    if open_date_norm and calendar_start:
        t1 = max(open_date_norm, calendar_start)
    elif open_date_norm:
        t1 = open_date_norm
    # open_date 为 None 时 t1 保持 None，不使用 calendar_start 作为 fallback

    # T2 = min(expire_date, latest_trading)
    t2 = None
    if expire_date_norm and latest_trading:
        t2 = min(expire_date_norm, latest_trading)
    elif latest_trading:
        t2 = latest_trading
    elif expire_date_norm:
        t2 = expire_date_norm

    # 写入调试字段
    result['_debug'] = {
        'open_date_raw':         open_date_norm,
        'expire_date_raw':       expire_date_norm,
        'calendar_start':        calendar_start,
        'latest_trading':        latest_trading,
        't1':                    t1,
        't2':                    t2,
        'no_open_date_skipped':  result['no_open_date'],  # True 表示前缺失检测已跳过
    }

    # ── 7. 前缺失检测（T1 → cache_start）────────────────────────
    if t1 is not None and cache_start is not None and cache_start > t1:
        head_missing = len([
            d for d in trading_dates_sorted
            if t1 <= d < cache_start
        ])
        result['head_missing'] = head_missing

    # ── 8. 后缺失检测（cache_end → T2）──────────────────────────
    if t2 is not None and cache_end is not None and cache_end < t2:
        tail_missing = len([
            d for d in trading_dates_sorted
            if cache_end < d <= t2
        ])
        result['tail_missing'] = tail_missing

    # ── 9. 计算 smart download 所需的缺口段信息 ───────────────
    if result['has_cache'] and cache_start and cache_end:
        actual_dates = get_cached_dates(symbol, period)

        # 8a. gap_segments：缓存范围内的中间缺口段
        result['gap_segments'] = calc_gap_segments(
            actual_dates, trading_dates_sorted, cache_start, cache_end
        )
        # 统计每段缺口的交易日数，存入 _debug 供 -v 展示
        gap_counts = []
        for gs, ge in result['gap_segments']:
            gs_norm = f"{gs[:4]}-{gs[4:6]}-{gs[6:8]}"
            ge_norm = f"{ge[:4]}-{ge[4:6]}-{ge[6:8]}"
            cnt = len([d for d in trading_dates_sorted if gs_norm <= d <= ge_norm])
            gap_counts.append(cnt)
        result['_debug']['gap_segment_counts'] = gap_counts

        # 8b. head_gap_segments：T1 到缓存起始之间的缺失段
        # 注意：no_open_date 时 head_missing=0，此处不会进入
        if result['head_missing'] > 0 and t1 is not None:
            result['head_gap_segments'] = calc_gap_segments(
                actual_dates, trading_dates_sorted, t1, cache_start
            )
        else:
            result['head_gap_segments'] = []

        # 8c. tail_start：后缺失的起始补充日期（缓存最新日期的下一个交易日）
        if result['tail_missing'] > 0:
            tail_start_date = None
            for d in trading_dates_sorted:
                if d > cache_end:
                    tail_start_date = d
                    break
            result['tail_start'] = tail_start_date.replace('-', '') if tail_start_date else None
        else:
            result['tail_start'] = None

    return result


def batch_validate(
    symbol_list: List[str],
    period: str,
    sub_type_config,
    trading_dates_sorted: List[str],
    instrument_df: Optional["pd.DataFrame"] = None,
    on_progress: Optional[callable] = None,
    stop_flag: Optional[callable] = None,
) -> List[Dict]:
    """
    批量对股票池执行全面健康检查。

    Args:
        symbol_list:           股票代码列表
        period:                数据周期
        sub_type_config:       SubTypeConfig 实例
        trading_dates_sorted:  已排序的交易日历（'YYYY-MM-DD' 格式）
        instrument_df:         合约信息 DataFrame（索引为 symbol），None 时跳过前缺失检测
        on_progress:           进度回调 (done: int, total: int)
        stop_flag:             停止检查函数，返回 True 时停止

    Returns:
        list[dict]，每项为 validate_symbol 的返回字典
    """
    total = len(symbol_list)
    results: List[Dict] = []

    for idx, symbol in enumerate(symbol_list):
        if stop_flag and stop_flag():
            break

        results.append(
            validate_symbol(symbol, period, sub_type_config, trading_dates_sorted, instrument_df)
        )

        if on_progress:
            on_progress(idx + 1, total)

    return results


def count_date_anomaly(results: List[Dict]) -> int:
    """
    统计 batch_validate 结果中存在日期异常的股票数量。

    Args:
        results: batch_validate 返回的结果列表

    Returns:
        存在日期异常的股票数量
    """
    return sum(1 for r in results if r.get('date_anomaly', False))
