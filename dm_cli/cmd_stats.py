# -*- coding: utf-8 -*-
"""
dm_cli/cmd_stats.py — stats 子命令实现

包含：cmd_stats、cmd_stats_detail、_list_valid_types、_apply_limit、
      _detail_kline、_detail_calendar、_detail_instrument、
      _detail_members、_detail_sector_list、_detail_generic
"""

import sys

from dm_cli.common import (
    _ok, _warn, _err, _info, _header, _load_service,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
)


# ──────────────────────────────────────────────────────────────────
# 辅助工具
# ──────────────────────────────────────────────────────────────────

def _list_valid_types() -> list:
    """返回所有合法的 asset_type/sub_type 组合列表"""
    try:
        from data_manager.asset_types import ENABLED_ASSET_TYPES
        result = []
        for at in ENABLED_ASSET_TYPES:
            for st in at.sub_types:
                result.append(f"{at.asset_type}/{st.sub_type}")
        return result
    except Exception:
        return []


def _apply_limit(data: list, limit: int) -> tuple:
    """
    按 limit 截断列表。
    返回 (截断后的列表, 总数, 是否被截断)
    limit <= 0 表示全量。
    """
    total = len(data)
    if limit <= 0:
        return data, total, False
    if total > limit:
        return data[:limit], total, True
    return data, total, False


# ──────────────────────────────────────────────────────────────────
# 主命令入口
# ──────────────────────────────────────────────────────────────────

def cmd_stats(args):
    """查看本地缓存统计信息（或二级品类明细）"""
    # 指定了 --asset 或 --sub 时，进入明细模式
    if getattr(args, 'asset', None) or getattr(args, 'sub', None):
        cmd_stats_detail(args)
        return

    _header("📊 本地缓存统计")
    service = _load_service()
    stats = service.get_cache_statistics()

    if not stats:
        _warn("无法获取缓存统计，请检查 data_manager 是否正确安装")
        return

    # ── 基础信息 ──────────────────────────────────────────────────
    total_mb = stats.get('total_size_mb', 0)
    total_gb = total_mb / 1024
    is_over = stats.get('is_over_threshold', False)
    size_str = f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_mb:.1f} MB"
    warn_str = f"  {_YELLOW}⚠ 已超过 5GB 警告阈值{_RESET}" if is_over else ""

    print(f"\n  缓存目录：{_CYAN}{stats.get('cache_root', 'N/A')}{_RESET}")
    print(f"  总缓存大小：{_BOLD}{size_str}{_RESET}{warn_str}")
    print(f"  全局数据范围：{stats.get('global_start_date', 'N/A')} ~ {stats.get('global_end_date', 'N/A')}")

    # ── 一级品类分组统计 ──────────────────────────────────────────
    asset_types = stats.get('asset_types', {})
    if asset_types:
        print(f"\n  {'─'*60}")
        print(f"  一级品类统计：\n")
        for at_key, at_info in asset_types.items():
            enabled = at_info.get('enabled', False)
            display = at_info.get('display_name', at_key)
            at_mb = at_info.get('size_mb', 0)
            at_size = f"{at_mb/1024:.2f} GB" if at_mb >= 1024 else f"{at_mb:.1f} MB"
            at_count = at_info.get('symbol_count', 0)
            at_start = at_info.get('start_date') or '—'
            at_end   = at_info.get('end_date')   or '—'
            at_range = f"{at_start} ~ {at_end}" if at_start != '—' else '—'
            at_sync  = at_info.get('last_sync') or '—'
            if at_sync and at_sync != '—' and len(at_sync) >= 16:
                at_sync = at_sync[:16]

            if not enabled:
                print(f"    {_YELLOW}{at_key}{_RESET}  {display}  （预留，未启用）")
            else:
                detail = f"{at_count} 只  {at_size}  {at_range}"
                if at_sync != '—':
                    detail += f"  同步于 {at_sync}"
                # 有任意子类有数据（或 symbol_count > 0）即显示 ✓
                sub_types_data = at_info.get('sub_types', {})
                has_any_data = at_count > 0 or any(
                    (v.get('symbol_count', 0) or v.get('record_count', 0) or v.get('file_count', 0)) > 0
                    for v in sub_types_data.values()
                )
                status = f"{_GREEN}✓{_RESET}" if has_any_data else f"{_YELLOW}✗{_RESET}"
                print(f"    {status} {at_key}  {display}  {detail}")

                # 打印二级子类明细（已注册的子类全部展示，无数据的显示"未同步"）
                sub_types = at_info.get('sub_types', {})
                try:
                    from data_manager.asset_types import get_asset_type as _get_at
                    _at_cfg = _get_at(at_key)
                    registered_sub_types = [st.sub_type for st in _at_cfg.sub_types] if _at_cfg else list(sub_types.keys())
                except Exception:
                    registered_sub_types = list(sub_types.keys())

                for sub_key in registered_sub_types:
                    sub_info = sub_types.get(sub_key)
                    # 查找 display_name
                    try:
                        _at_cfg2 = _get_at(at_key)
                        _st_cfg = _at_cfg2.get_sub_type(sub_key) if _at_cfg2 else None
                        sub_display = _st_cfg.display_name if _st_cfg else sub_key
                    except Exception:
                        sub_display = sub_info.get('display_name', sub_key) if sub_info else sub_key

                    if sub_info is None:
                        # 已注册但无数据
                        print(f"        {_YELLOW}✗{_RESET} {sub_key}  {sub_display}  {_YELLOW}未同步{_RESET}")
                        continue

                    sub_mb = sub_info.get('size_mb', 0)
                    sub_size = f"{sub_mb/1024:.2f} GB" if sub_mb >= 1024 else f"{sub_mb:.1f} MB"

                    if sub_key == 'kline':
                        sym_cnt = sub_info.get('symbol_count', 0)
                        periods_list = sub_info.get('periods', [])
                        periods_str = '/'.join(sorted(periods_list)) if periods_list else '—'
                        sub_detail = f"{sym_cnt} 只  {sub_size}  周期: {periods_str}"
                        has_data = sym_cnt > 0
                        sub_status = f"{_GREEN}✓{_RESET}" if has_data else f"{_YELLOW}✗{_RESET}"
                        print(f"        {sub_status} {sub_key}  {sub_display}  {sub_detail}")
                        # 展开各周期明细
                        at_periods = at_info.get('periods', {})
                        if at_periods:
                            col_p = 8; col_c = 7; col_s = 10; col_r = 25; col_sy = 19
                            hdr = (f"          {'周期':<{col_p}} {'股票数':>{col_c}} {'大小':>{col_s}}"
                                   f"  {'数据范围':<{col_r}} {'最后同步':>{col_sy}}")
                            sep_line = (f"          {'─'*col_p} {'─'*col_c} {'─'*col_s}"
                                        f"  {'─'*col_r} {'─'*col_sy}")
                            print(hdr)
                            print(sep_line)
                            for p_key in sorted(at_periods):
                                p_info = at_periods[p_key]
                                p_mb = p_info.get('size_mb', 0)
                                p_size = f"{p_mb/1024:.2f} GB" if p_mb >= 1024 else f"{p_mb:.1f} MB"
                                p_start = p_info.get('start_date') or 'N/A'
                                p_end   = p_info.get('end_date')   or 'N/A'
                                p_range = f"{p_start} ~ {p_end}"
                                p_sync  = p_info.get('last_sync') or '—'
                                if p_sync and p_sync != '—' and len(p_sync) >= 16:
                                    p_sync = p_sync[:16]
                                print(f"          {p_key:<{col_p}} {p_info.get('symbol_count',0):>{col_c}}"
                                      f" {p_size:>{col_s}}  {p_range:<{col_r}} {p_sync:>{col_sy}}")
                    elif sub_key == 'calendar':
                        aux = stats.get('aux_data', {})
                        cal_count = aux.get('calendar_count', 0)
                        cal_range = aux.get('calendar_range')
                        rec_cnt = sub_info.get('record_count', cal_count)
                        has_data = rec_cnt > 0
                        sub_status = f"{_GREEN}✓{_RESET}" if has_data else f"{_YELLOW}✗{_RESET}"
                        sub_detail = f"{rec_cnt} 条  {sub_size}"
                        if cal_range:
                            sub_detail += f"  ({cal_range})"
                        print(f"        {sub_status} {sub_key}  {sub_display}  {sub_detail}")
                    elif sub_key == 'instrument':
                        aux = stats.get('aux_data', {})
                        inst_count = aux.get('instrument_count', 0)
                        rec_cnt = sub_info.get('record_count', inst_count)
                        has_data = rec_cnt > 0
                        sub_status = f"{_GREEN}✓{_RESET}" if has_data else f"{_YELLOW}✗{_RESET}"
                        sub_detail = f"{rec_cnt} 条  {sub_size}"
                        print(f"        {sub_status} {sub_key}  {sub_display}  {sub_detail}")
                    else:
                        rec_cnt = sub_info.get('record_count', 0)
                        file_cnt = sub_info.get('file_count', 0)
                        sub_detail = f"{rec_cnt} 条  {sub_size}  ({file_cnt} 个文件)"
                        has_data = (sub_info.get('symbol_count', 0) or rec_cnt or file_cnt) > 0
                        sub_status = f"{_GREEN}✓{_RESET}" if has_data else f"{_YELLOW}✗{_RESET}"
                        print(f"        {sub_status} {sub_key}  {sub_display}  {sub_detail}")


# ──────────────────────────────────────────────────────────────────
# stats detail 子命令
# ──────────────────────────────────────────────────────────────────

def cmd_stats_detail(args):
    """查看指定二级品类的数据明细"""
    at_key = getattr(args, 'asset', None) or 'stock'
    sub_key = getattr(args, 'sub', None) or 'kline'
    limit = getattr(args, 'detail_limit', 50)
    period_filter = getattr(args, 'detail_period', None)

    # 校验品类是否存在且已启用
    try:
        from data_manager.asset_types import get_asset_type
        at_cfg = get_asset_type(at_key)
    except Exception as e:
        _err(f"无法加载品类配置：{e}")
        sys.exit(1)

    if at_cfg is None:
        _err(f"未知品类：{at_key!r}")
        valid = _list_valid_types()
        if valid:
            print(f"\n  合法值：")
            for v in valid:
                print(f"    {v}")
        sys.exit(1)

    if not at_cfg.enabled:
        _err(f"品类 {at_key!r} 尚未启用（预留品类）")
        sys.exit(1)

    st_cfg = at_cfg.get_sub_type(sub_key)
    if st_cfg is None:
        _err(f"品类 {at_key!r} 下不存在子类 {sub_key!r}")
        valid = [f"{at_key}/{st.sub_type}" for st in at_cfg.sub_types]
        print(f"\n  {at_key} 下的合法子类：")
        for v in valid:
            print(f"    {v}")
        sys.exit(1)

    sub_display = st_cfg.display_name

    _header(f"📋 {at_cfg.display_name} / {sub_display}  明细")

    # 根据子类分发到对应展示函数
    symbols_filter = None
    if sub_key == 'kline':
        symbols_str = getattr(args, 'symbols', None)
        if symbols_str and symbols_str.strip():
            symbols_filter = [s.strip() for s in symbols_str.split(',') if s.strip()]
        _detail_kline(at_key, period_filter, limit, symbols_filter)
    elif sub_key == 'calendar':
        _detail_calendar(limit)
    elif sub_key == 'instrument':
        _detail_instrument(limit)
    elif sub_key == 'members':
        _detail_members(at_key, limit)
    elif sub_key == 'sector_list':
        _detail_sector_list(at_key, limit)
    else:
        _detail_generic(at_key, sub_key, limit)


# ──────────────────────────────────────────────────────────────────
# 各子类明细展示函数
# ──────────────────────────────────────────────────────────────────

def _detail_kline(at_key: str, period_filter: str, limit: int, symbols_filter: list = None):
    """展示 kline 子类明细：每只股票一行，含周期/记录数/起止日期/文件大小"""
    import pandas as pd
    from pathlib import Path

    cache_root = Path.home() / ".quant" / "cache"
    kline_dir = cache_root / at_key / "kline"

    # 兼容旧路径：stock 品类的 kline 数据可能在 cache/kline/（旧路径）
    old_kline_dir = cache_root / "kline"
    if at_key == 'stock':
        # 检查新路径下是否有周期子目录（排除 sync_meta.parquet 等非目录文件）
        has_period_dirs = kline_dir.exists() and any(
            p.is_dir() for p in kline_dir.iterdir()
        ) if kline_dir.exists() else False
        if not has_period_dirs and old_kline_dir.exists():
            kline_dir = old_kline_dir

    if not kline_dir.exists():
        _warn("暂无数据，请先同步（运行 sync 命令）")
        return

    # 尝试加载 instrument 以获取股票名称
    name_map = {}
    try:
        from data_manager.aux_data import load_instrument_detail
        detail = load_instrument_detail()
        for sym, info in detail.items():
            name = info.get('name') or info.get('stock_name') or ''
            name_map[sym] = name
            # 同时建立不带后缀的映射（如 000001.SZ → 000001）
            base = sym.split('.')[0] if '.' in sym else sym
            if base not in name_map:
                name_map[base] = name
    except Exception:
        pass

    # 扫描各周期目录
    # 结构：kline/{period}/{market}/{symbol}.parquet
    # 按股票聚合：{symbol: {period: {records, start, end, size_bytes}}}
    symbol_data = {}  # {symbol: {period: {...}}}

    for period_dir in sorted(kline_dir.iterdir()):
        if not period_dir.is_dir():
            continue
        period = period_dir.name
        if period_filter and period != period_filter:
            continue

        for market_dir in period_dir.iterdir():
            if not market_dir.is_dir():
                continue
            for pq_file in market_dir.glob("*.parquet"):
                symbol = pq_file.stem
                size_bytes = pq_file.stat().st_size
                records = 0
                start_date = None
                end_date = None
                try:
                    df = pd.read_parquet(pq_file, engine="pyarrow")
                    records = len(df)
                    if not df.empty:
                        if not isinstance(df.index, pd.DatetimeIndex):
                            df.index = pd.to_datetime(df.index)
                        start_date = str(df.index.min().date())
                        end_date = str(df.index.max().date())
                except Exception:
                    pass

                if symbol not in symbol_data:
                    symbol_data[symbol] = {}
                symbol_data[symbol][period] = {
                    'records': records,
                    'start': start_date,
                    'end': end_date,
                    'size_bytes': size_bytes,
                }

    # 按 --symbols 过滤
    if symbols_filter:
        symbol_data = {s: v for s, v in symbol_data.items() if s in symbols_filter}

    if not symbol_data:
        if symbols_filter:
            _warn(f"指定的股票代码在本地缓存中均无数据")
        elif period_filter:
            _warn(f"周期 {period_filter!r} 暂无数据，请先同步")
        else:
            _warn("暂无数据，请先同步（运行 sync 命令）")
        return

    # 构建展示行
    rows = []
    for symbol in sorted(symbol_data.keys()):
        periods_info = symbol_data[symbol]
        periods_str = '/'.join(sorted(periods_info.keys()))
        total_records = sum(v['records'] for v in periods_info.values())
        total_bytes = sum(v['size_bytes'] for v in periods_info.values())
        size_str = f"{total_bytes/1024/1024:.1f} MB" if total_bytes >= 1024*1024 else f"{total_bytes/1024:.1f} KB"
        # 起止日期取所有周期的最早/最晚
        starts = [v['start'] for v in periods_info.values() if v['start']]
        ends = [v['end'] for v in periods_info.values() if v['end']]
        start_str = min(starts) if starts else 'N/A'
        end_str = max(ends) if ends else 'N/A'
        name = name_map.get(symbol, '')
        rows.append((symbol, name, periods_str, total_records, start_str, end_str, size_str))

    rows_to_show, total, truncated = _apply_limit(rows, limit)

    # 打印表头
    print()
    col_sym = 14; col_name = 8; col_per = 8; col_rec = 8; col_range = 25; col_size = 10
    hdr = (f"  {'代码':<{col_sym}} {'名称':<{col_name}} {'周期':<{col_per}}"
           f" {'记录数':>{col_rec}}  {'数据范围':<{col_range}} {'大小':>{col_size}}")
    sep = (f"  {'─'*col_sym} {'─'*col_name} {'─'*col_per}"
           f" {'─'*col_rec}  {'─'*col_range} {'─'*col_size}")
    print(hdr)
    print(sep)
    for symbol, name, periods_str, records, start_str, end_str, size_str in rows_to_show:
        range_str = f"{start_str} ~ {end_str}"
        print(f"  {symbol:<{col_sym}} {name:<{col_name}} {periods_str:<{col_per}}"
              f" {records:>{col_rec}}  {range_str:<{col_range}} {size_str:>{col_size}}")

    if truncated:
        print(f"\n  {_YELLOW}仅显示前 {len(rows_to_show)} 条，共 {total} 条。使用 --limit 0 查看全部{_RESET}")
    else:
        print(f"\n  共 {total} 只股票")


def _detail_calendar(limit: int):
    """展示 calendar 子类明细：总条数+范围，分列展示日期"""
    try:
        from data_manager.aux_data import load_trading_calendar
        dates = load_trading_calendar()
    except Exception as e:
        _err(f"读取交易日历失败：{e}")
        return

    if not dates:
        _warn("暂无数据，请先同步（运行 sync-aux 命令）")
        return

    total = len(dates)
    start_d = dates[0] if dates else 'N/A'
    end_d = dates[-1] if dates else 'N/A'

    print(f"\n  共 {_BOLD}{total}{_RESET} 个交易日  ({start_d} ~ {end_d})\n")

    dates_to_show, _, truncated = _apply_limit(dates, limit)

    # 每行显示 6 个日期，列宽 12
    cols = 6
    col_w = 12
    for i in range(0, len(dates_to_show), cols):
        row = dates_to_show[i:i+cols]
        print("  " + "".join(f"{d:<{col_w}}" for d in row))

    if truncated:
        print(f"\n  {_YELLOW}仅显示前 {len(dates_to_show)} 条，共 {total} 条。使用 --limit 0 查看全部{_RESET}")


def _detail_instrument(limit: int):
    """展示 instrument 子类明细：代码、名称、上市日期、退市日、交易所、涨跌停、流通股本等"""
    try:
        from data_manager.aux_data import load_instrument_detail
        detail = load_instrument_detail()
    except Exception as e:
        _err(f"读取合约信息失败：{e}")
        return

    if not detail:
        _warn("暂无数据，请先同步（运行 sync-aux 命令）")
        return

    # 按代码排序
    rows = sorted(detail.items(), key=lambda x: x[0])
    rows_to_show, total, truncated = _apply_limit(rows, limit)

    # 检测数据是否包含扩展字段（兼容旧数据只有 name+instrument_status 的情况）
    sample = rows_to_show[0][1] if rows_to_show else {}
    has_extended = 'open_date' in sample or 'exchange_id' in sample

    print()
    if has_extended:
        # 扩展字段模式：展示完整信息
        columns = [
            ('name',             '名称',     10),
            ('exchange_id',      '交易所',    6),
            ('open_date',        '上市日期',  10),
            ('expire_date',      '退市日',    10),
            ('pre_close',        '前收价',    8),
            ('up_stop_price',    '涨停价',    8),
            ('down_stop_price',  '跌停价',    8),
            ('float_volume',     '流通股本(亿)', 12),
            ('instrument_status','停牌状态',  8),
            ('is_trading',       '可交易',    6),
        ]
        col_sym = 14
        col_widths = [col_sym] + [c[2] for c in columns]
        labels    = ['代码']   + [c[1] for c in columns]

        hdr = "  " + "  ".join(f"{lbl:<{w}}" for lbl, w in zip(labels, col_widths))
        sep = "  " + "  ".join("─" * w for w in col_widths)
        print(hdr)
        print(sep)

        for symbol, info in rows_to_show:
            # 流通股本转换为亿股
            fv = info.get('float_volume', 0) or 0
            fv_str = f"{fv/1e8:.2f}" if fv else ''
            # 退市日：99999999 或 0 显示为空
            ed = info.get('expire_date', 0) or 0
            ed_str = '' if ed in (0, 99999999) else str(ed)
            # 停牌状态
            st = info.get('instrument_status', 0) or 0
            st_str = '正常' if st <= 0 else f'停牌{st}天'
            # 可交易
            it = info.get('is_trading', True)
            it_str = '是' if it else '否'

            vals = [
                symbol,
                str(info.get('name', '') or '')[:10],
                str(info.get('exchange_id', '') or '')[:6],
                str(info.get('open_date', '') or '')[:10],
                ed_str[:10],
                f"{info.get('pre_close', 0) or 0:.2f}"[:8],
                f"{info.get('up_stop_price', 0) or 0:.2f}"[:8],
                f"{info.get('down_stop_price', 0) or 0:.2f}"[:8],
                fv_str[:12],
                st_str[:8],
                it_str[:6],
            ]
            print("  " + "  ".join(f"{v:<{w}}" for v, w in zip(vals, col_widths)))
    else:
        # 兼容旧数据：只有 name + instrument_status
        _warn("当前缓存为旧格式（仅含名称和停牌状态），建议重新运行 sync-aux 以获取完整字段")
        col_sym = 14
        col_widths = [col_sym, 16, 12]
        labels = ['代码', '名称', '停牌状态']
        hdr = "  " + "  ".join(f"{lbl:<{w}}" for lbl, w in zip(labels, col_widths))
        sep = "  " + "  ".join("─" * w for w in col_widths)
        print(hdr)
        print(sep)
        for symbol, info in rows_to_show:
            st = info.get('instrument_status', 0) or 0
            st_str = '正常' if st <= 0 else f'停牌{st}天'
            vals = [symbol, str(info.get('name', '') or '')[:16], st_str]
            print("  " + "  ".join(f"{v:<{w}}" for v, w in zip(vals, col_widths)))

    if truncated:
        print(f"\n  {_YELLOW}仅显示前 {len(rows_to_show)} 条，共 {total} 条。使用 --limit 0 查看全部{_RESET}")
    else:
        print(f"\n  共 {total} 只股票")


def _detail_members(at_key: str, limit: int):
    """展示 members 子类明细：板块名称、成分股数量、文件大小，按成分股数量降序"""
    import pandas as pd
    from pathlib import Path

    cache_root = Path.home() / ".quant" / "cache"
    members_dir = cache_root / at_key / "members"

    if not members_dir.exists():
        _warn("暂无数据，请先同步（运行 sync-industry 命令）")
        return

    rows = []
    for pq_file in sorted(members_dir.glob("*.parquet")):
        sector_name = pq_file.stem
        size_bytes = pq_file.stat().st_size
        size_str = f"{size_bytes/1024:.1f} KB" if size_bytes < 1024*1024 else f"{size_bytes/1024/1024:.1f} MB"
        count = 0
        try:
            df = pd.read_parquet(pq_file, engine="pyarrow")
            count = len(df)
        except Exception:
            pass
        rows.append((sector_name, count, size_str))

    if not rows:
        _warn("暂无数据，请先同步（运行 sync-industry 命令）")
        return

    # 按成分股数量降序
    rows.sort(key=lambda x: x[1], reverse=True)
    rows_to_show, total, truncated = _apply_limit(rows, limit)

    print()
    col_name = 30; col_cnt = 8; col_size = 10
    hdr = f"  {'板块名称':<{col_name}} {'成分股数':>{col_cnt}} {'文件大小':>{col_size}}"
    sep = f"  {'─'*col_name} {'─'*col_cnt} {'─'*col_size}"
    print(hdr)
    print(sep)
    for sector_name, count, size_str in rows_to_show:
        print(f"  {sector_name:<{col_name}} {count:>{col_cnt}} {size_str:>{col_size}}")

    if truncated:
        print(f"\n  {_YELLOW}仅显示前 {len(rows_to_show)} 条，共 {total} 个板块。使用 --limit 0 查看全部{_RESET}")
    else:
        print(f"\n  共 {total} 个板块")


def _detail_sector_list(at_key: str, limit: int):
    """展示 sector_list 子类明细：板块总数及板块名称列表"""
    import pandas as pd
    from pathlib import Path

    cache_root = Path.home() / ".quant" / "cache"
    pq_file = cache_root / at_key / "sector_list" / "sector_list.parquet"

    if not pq_file.exists():
        _warn("暂无数据，请先同步（运行 sync-industry 命令）")
        return

    try:
        df = pd.read_parquet(pq_file, engine="pyarrow")
    except Exception as e:
        _err(f"读取板块列表失败：{e}")
        return

    if df.empty:
        _warn("板块列表为空，请重新同步")
        return

    total = len(df)
    print(f"\n  共 {_BOLD}{total}{_RESET} 个板块\n")

    # 尝试找到板块名称列
    name_col = None
    for col in ['sector_name', 'name', 'sector', '板块名称']:
        if col in df.columns:
            name_col = col
            break
    if name_col is None and len(df.columns) > 0:
        name_col = df.columns[0]

    if name_col:
        names = df[name_col].tolist()
        names_to_show, _, truncated = _apply_limit(names, limit)
        # 每行显示 3 个板块名称
        cols = 3
        col_w = 28
        for i in range(0, len(names_to_show), cols):
            row = names_to_show[i:i+cols]
            print("  " + "".join(f"{str(n):<{col_w}}" for n in row))
        if truncated:
            print(f"\n  {_YELLOW}仅显示前 {len(names_to_show)} 条，共 {total} 条。使用 --limit 0 查看全部{_RESET}")
    else:
        _warn("无法识别板块名称列，原始列名：" + str(list(df.columns)))


def _detail_generic(at_key: str, sub_key: str, limit: int):
    """通用兜底展示：扫描子类目录下所有 Parquet 文件，展示文件名、记录数、文件大小"""
    import pandas as pd
    from pathlib import Path

    cache_root = Path.home() / ".quant" / "cache"
    sub_dir = cache_root / at_key / sub_key

    if not sub_dir.exists():
        _warn(f"暂无数据（目录不存在：{sub_dir}）")
        return

    rows = []
    for pq_file in sorted(sub_dir.rglob("*.parquet")):
        rel_name = str(pq_file.relative_to(sub_dir))
        size_bytes = pq_file.stat().st_size
        size_str = f"{size_bytes/1024:.1f} KB" if size_bytes < 1024*1024 else f"{size_bytes/1024/1024:.1f} MB"
        records = 0
        try:
            df = pd.read_parquet(pq_file, engine="pyarrow")
            records = len(df)
        except Exception:
            pass
        rows.append((rel_name, records, size_str))

    if not rows:
        _warn("暂无数据，请先同步")
        return

    rows_to_show, total, truncated = _apply_limit(rows, limit)

    print()
    col_name = 40; col_rec = 10; col_size = 10
    hdr = f"  {'文件名':<{col_name}} {'记录数':>{col_rec}} {'大小':>{col_size}}"
    sep = f"  {'─'*col_name} {'─'*col_rec} {'─'*col_size}"
    print(hdr)
    print(sep)
    for fname, records, size_str in rows_to_show:
        print(f"  {fname:<{col_name}} {records:>{col_rec}} {size_str:>{col_size}}")

    if truncated:
        print(f"\n  {_YELLOW}仅显示前 {len(rows_to_show)} 条，共 {total} 个文件。使用 --limit 0 查看全部{_RESET}")
    else:
        print(f"\n  共 {total} 个文件")
