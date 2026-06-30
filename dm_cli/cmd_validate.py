# -*- coding: utf-8 -*-
"""
dm_cli/cmd_validate.py — validate 子命令实现

包含：cmd_validate、_cmd_validate_industry_sector_list、_cmd_validate_industry_members
"""

import sys

from dm_cli.common import (
    _ok, _warn, _err, _info, _header, _load_service, _resolve_symbols,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
    CliCallbacks,
)


# ──────────────────────────────────────────────────────────────────
# industry 子类校验辅助函数
# ──────────────────────────────────────────────────────────────────

def _cmd_validate_industry_sector_list():
    """校验 industry/sector_list 数据健康状态"""
    from pathlib import Path
    import pandas as pd

    cache_root = Path.home() / "quant" / "cache"
    rel_path   = "industry/sector_list/sector_list.parquet"
    file_path  = cache_root / rel_path

    _header("🔍 数据健康检查")
    _info("品类：industry/sector_list")
    print()

    # ── 1. 存在性 ──────────────────────────────────────────────
    if not file_path.exists():
        _err("❌ 文件不存在：未同步板块分类信息")
        _warn("修复建议：python dm_cli.py sync --asset industry --sub sector_list")
        sys.exit(1)

    # ── 2. 可读性 + 字段完整度 + 记录数 ───────────────────────
    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
    except Exception as e:
        _err(f"❌ 文件损坏，无法读取：{e}")
        _warn("修复建议：python dm_cli.py sync --asset industry --sub sector_list")
        sys.exit(1)

    record_count = len(df)
    required_cols = ['sector_name', 'updated_at']
    missing_cols  = [c for c in required_cols if c not in df.columns]

    print(f"  {'─'*50}")
    print(f"  校验结果（industry/sector_list）：")
    print(f"    文件路径：{file_path}")
    print(f"    记录数：{record_count} 个板块")

    has_problem = False

    if missing_cols:
        has_problem = True
        print(f"    🔴 缺失字段：{', '.join(missing_cols)}")
    else:
        print(f"    ✅ 字段完整：{', '.join(required_cols)}")

    if record_count == 0:
        has_problem = True
        print(f"    🔴 数据为空：文件存在但无记录")
    else:
        # 显示更新时间
        if 'updated_at' in df.columns:
            try:
                updated_at = df['updated_at'].iloc[0]
                print(f"    最后同步：{updated_at}")
            except Exception:
                pass

    print(f"  {'─'*50}")

    if has_problem:
        _warn("修复建议：python dm_cli.py sync --asset industry --sub sector_list")
    else:
        _ok("sector_list 数据健康，无异常")


def _cmd_validate_industry_members():
    """校验 industry/members 数据健康状态"""
    from pathlib import Path
    import pandas as pd

    cache_root   = Path.home() / ".quant" / "cache"
    members_dir  = cache_root / "industry" / "members"

    _header("🔍 数据健康检查")
    _info("品类：industry/members")
    print()

    # ── 1. 目录存在性 ──────────────────────────────────────────
    if not members_dir.exists():
        _err("❌ 目录不存在：未同步成分股数据")
        _warn("修复建议：python dm_cli.py sync --asset industry --sub members")
        sys.exit(1)

    parquet_files = sorted(members_dir.glob("*.parquet"))
    total_files   = len(parquet_files)

    if total_files == 0:
        _err("❌ 目录为空：未找到任何成分股文件")
        _warn("修复建议：python dm_cli.py sync --asset industry --sub members")
        sys.exit(1)

    # ── 2. 逐文件校验 ─────────────────────────────────────────
    required_cols  = ['symbol', 'sector_name']
    total_symbols  = 0
    empty_files    = []
    corrupt_files  = []
    missing_fields = []

    for fp in parquet_files:
        try:
            df = pd.read_parquet(fp, engine="pyarrow")
        except Exception as e:
            corrupt_files.append((fp.stem, str(e)))
            continue

        if df.empty:
            empty_files.append(fp.stem)
            continue

        total_symbols += len(df)
        miss = [c for c in required_cols if c not in df.columns]
        if miss:
            missing_fields.append((fp.stem, miss))

    # ── 3. 汇总输出 ────────────────────────────────────────────
    healthy_files = total_files - len(empty_files) - len(corrupt_files) - len(missing_fields)

    print(f"  {'─'*50}")
    print(f"  校验结果（industry/members）：")
    print(f"    板块文件总数：{total_files}")
    print(f"    ✅ 健康文件：{healthy_files}")
    print(f"    总成分股数：{total_symbols}")

    has_problem = False

    if corrupt_files:
        has_problem = True
        print(f"    🔴 损坏文件（{len(corrupt_files)} 个）：")
        for name, err in corrupt_files[:10]:
            print(f"      {name}：{err}")
        if len(corrupt_files) > 10:
            _warn(f"  （仅显示前 10 个，共 {len(corrupt_files)} 个）")

    if empty_files:
        has_problem = True
        print(f"    🟠 空文件（{len(empty_files)} 个）：")
        for name in empty_files[:10]:
            print(f"      {name}")
        if len(empty_files) > 10:
            _warn(f"  （仅显示前 10 个，共 {len(empty_files)} 个）")

    if missing_fields:
        has_problem = True
        print(f"    🔴 字段不完整（{len(missing_fields)} 个）：")
        for name, miss in missing_fields[:10]:
            print(f"      {name}：缺失 {', '.join(miss)}")
        if len(missing_fields) > 10:
            _warn(f"  （仅显示前 10 个，共 {len(missing_fields)} 个）")

    print(f"  {'─'*50}")

    if has_problem:
        _warn("修复建议：python dm_cli.py sync --asset industry --sub members")
    else:
        _ok("members 数据健康，无异常")


# ──────────────────────────────────────────────────────────────────
# 主命令入口
# ──────────────────────────────────────────────────────────────────

def cmd_validate(args):
    """对板块成分股执行全面数据健康检查"""
    # ── 解析 --asset / --sub，默认 stock/kline ─────────────────
    asset = (getattr(args, 'asset', None) or 'stock').strip()
    sub   = (getattr(args, 'sub',   None) or 'kline').strip()

    # ── 按品类/子类分发 ────────────────────────────────────────
    if asset == 'industry' and sub == 'sector_list':
        _cmd_validate_industry_sector_list()
        return
    if asset == 'industry' and sub == 'members':
        _cmd_validate_industry_members()
        return

    if asset not in ('stock', 'index') or sub != 'kline':
        _warn(f"validate 暂未实现 {asset}/{sub} 的健康检查逻辑，跳过")
        _info("当前支持：stock/kline | index/kline | industry/sector_list | industry/members")
        sys.exit(0)

    # ── 校验 kline 必填参数 ────────────────────────────────────
    if not getattr(args, 'period', None):
        _err(f"校验 {asset}/kline 需要 --period 参数（数据周期，如 1d）")
        sys.exit(1)

    service = _load_service()

    # ── index/kline：优先从本地指数缓存读取标的列表 ────────────
    if asset == 'index':
        sector = getattr(args, 'sector', None)
        symbols_str = getattr(args, 'symbols', None)
        if sector:
            from dm_cli.common import _resolve_sector
            symbols = _resolve_sector(service, sector)
            source_label = f"板块：{sector}（{len(symbols)} 只）"
        elif symbols_str:
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            source_label = f"代码：{', '.join(symbols[:3])}{'等' if len(symbols) > 3 else ''}（{len(symbols)} 只）"
        else:
            from data_manager.aux_data import load_index_instrument_detail
            cached = load_index_instrument_detail()
            if cached:
                symbols = sorted(cached.keys())
                source_label = f"来源：本地指数缓存（{len(symbols)} 只）"
            else:
                _warn("本地无指数缓存，请先执行：python dm_cli.py download --asset index --sub instrument")
                sys.exit(1)
    else:
        symbols, source_label = _resolve_symbols(args, service)
    period  = args.period.strip()

    _header(f"🔍 全面数据健康检查")
    _info(f"品类：{asset}/{sub}")
    _info(source_label)
    _info(f"周期：{period}")
    print()

    # ── 获取 SubTypeConfig ─────────────────────────────────────
    try:
        from data_manager.asset_types import get_asset_type
        at_cfg = get_asset_type(asset)
        if at_cfg is None:
            _err(f"未知品类：{asset}")
            sys.exit(1)
        sub_cfg = at_cfg.get_sub_type(sub)
        if sub_cfg is None:
            _err(f"未知子类：{sub}")
            sys.exit(1)
    except ImportError as e:
        _err(f"无法导入 asset_types 模块：{e}")
        sys.exit(1)

    # ── 执行校验 ───────────────────────────────────────────────
    show_detail = getattr(args, 'detail', False)

    def _on_progress(done, total):
        if total > 0 and (done % max(1, total // 20) == 0 or done == total):
            print(f"\r  校验进度：{done}/{total}", end="", flush=True)

    cb = CliCallbacks(show_progress=False)
    cb.on_progress = _on_progress

    result = service.validate_kline(
        params={
            'stock_list':       symbols,
            'period':           period,
            'sub_type_config':  sub_cfg,
            'asset_type':       asset,
        },
        callbacks=cb,
    )
    print()  # 换行

    if not result.get('results') and not result.get('success', True) is False:
        _err("校验失败，请检查依赖数据是否就绪")
        sys.exit(1)

    results_list = result.get('results', [])

    # ── 汇总统计 ───────────────────────────────────────────────
    total           = result.get('total', len(results_list))
    cnt_no_cache    = result.get('no_cache', 0)
    cnt_field       = result.get('field_error', 0)
    cnt_type        = result.get('type_error', 0)
    cnt_head        = result.get('head_missing', 0)
    cnt_tail        = result.get('tail_missing', 0)
    cnt_gap         = result.get('gap', 0)
    cnt_anomaly     = result.get('date_anomaly', 0)
    cnt_no_open_date = result.get('no_open_date', 0)
    cnt_healthy     = result.get('healthy', 0)

    print(f"\n  {'─'*50}")
    print(f"  校验汇总（{period}）：")
    print(f"    总扫描：{total} 只")
    print(f"    ✅ 完全健康：{cnt_healthy} 只")
    print(f"    ⬜ 无缓存：{cnt_no_cache} 只")
    print(f"    🔴 字段不完整：{cnt_field} 只")
    print(f"    🟠 类型异常：{cnt_type} 只")
    print(f"    🟡 前缺失：{cnt_head} 只")
    print(f"    🟡 后缺失：{cnt_tail} 只")
    print(f"    🟡 中间缺口：{cnt_gap} 只")
    if cnt_anomaly > 0:
        print(f"    🔴 日期异常：{cnt_anomaly} 只")
    if cnt_no_open_date > 0:
        print(f"    ⚠️  上市日期缺失：{cnt_no_open_date} 只")
    print(f"  {'─'*50}")

    has_problem = (cnt_no_cache + cnt_field + cnt_type + cnt_head + cnt_tail + cnt_gap + cnt_anomaly + cnt_no_open_date) > 0

    if not has_problem:
        _ok("所有股票数据健康，无异常")
        return

    # ── 按问题类型分组展示（默认最多 50 只）─────────────────────
    MAX_SHOW = 50
    show_verbose = getattr(args, 'verbose', False)

    # 无缓存
    no_cache_list = [r for r in results_list if not r['has_cache']]
    if no_cache_list:
        print(f"\n  ⬜ 无缓存（{len(no_cache_list)} 只）：")
        for r in no_cache_list[:MAX_SHOW]:
            print(f"    {r['symbol']}")
        if len(no_cache_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(no_cache_list)} 只）")

    # 字段不完整
    field_err_list = [r for r in results_list if r['has_cache'] and not r['field_ok']]
    if field_err_list:
        print(f"\n  🔴 字段不完整（{len(field_err_list)} 只）：")
        for r in field_err_list[:MAX_SHOW]:
            missing_str = ', '.join(r['missing_fields'])
            print(f"    {r['symbol']:<16}  缺失列：{missing_str}")
        if len(field_err_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(field_err_list)} 只）")

    # 类型异常
    type_err_list = [r for r in results_list if r['has_cache'] and not r['type_ok']]
    if type_err_list:
        print(f"\n  🟠 类型异常（{len(type_err_list)} 只）：")
        for r in type_err_list[:MAX_SHOW]:
            if show_detail:
                for te in r['type_errors']:
                    print(f"    {r['symbol']:<16}  列 {te['col']}：期望 {te['expected']}，实际 {te['actual']}")
            else:
                cols = ', '.join(te['col'] for te in r['type_errors'])
                print(f"    {r['symbol']:<16}  异常列：{cols}")
        if len(type_err_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(type_err_list)} 只）")

    # 前缺失
    head_list = [r for r in results_list if r['head_missing'] > 0]
    if head_list:
        print(f"\n  🟡 前缺失（{len(head_list)} 只）：")
        for r in head_list[:MAX_SHOW]:
            dbg = r.get('_debug', {})
            if show_detail:
                print(
                    f"    {r['symbol']:<16}  上市日：{r.get('open_date', '?')}  "
                    f"缓存起始：{r['cache_start']}  缺失 {r['head_missing']} 个交易日"
                )
            else:
                print(f"    {r['symbol']:<16}  缺失 {r['head_missing']} 个交易日（起始：{r['cache_start']}）")
            if show_verbose:
                t1  = dbg.get('t1')
                t2  = dbg.get('t2')
                od  = dbg.get('open_date_raw') or '无'
                ed  = dbg.get('expire_date_raw') or '无退市'
                cs  = dbg.get('calendar_start') or '无'
                lt  = dbg.get('latest_trading') or '无'
                print(f"      {'─'*56}")
                print(f"      [前缺失判断明细]")
                print(f"        open_date（上市日）  : {od}")
                print(f"        expire_date（退市日）: {ed}")
                print(f"        calendar_start      : {cs}")
                print(f"        latest_trading      : {lt}")
                print(f"        T1 = max(open_date, calendar_start) = {t1 or '无'}")
                print(f"        T2 = min(expire_date, latest_trading) = {t2 or '无'}")
                print(f"        cache_start         : {r['cache_start']}")
                print(f"        前缺失区间          : [{t1} , {r['cache_start']})  共 {r['head_missing']} 个交易日")
                segs = r.get('head_gap_segments', [])
                if segs:
                    segs_str = ', '.join(f"{s}~{e}" for s, e in segs[:5])
                    if len(segs) > 5:
                        segs_str += f" ...（共{len(segs)}段）"
                    print(f"        前缺失缺口段        : {segs_str}")
                print(f"      {'─'*56}")
        if len(head_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(head_list)} 只）")

    # 后缺失
    tail_list = [r for r in results_list if r['tail_missing'] > 0]
    if tail_list:
        print(f"\n  🟡 后缺失（{len(tail_list)} 只）：")
        for r in tail_list[:MAX_SHOW]:
            dbg = r.get('_debug', {})
            if show_detail:
                print(
                    f"    {r['symbol']:<16}  缓存最新：{r['cache_end']}  "
                    f"落后 {r['tail_missing']} 个交易日"
                )
            else:
                print(f"    {r['symbol']:<16}  落后 {r['tail_missing']} 个交易日（最新：{r['cache_end']}）")
            if show_verbose:
                t1  = dbg.get('t1')
                t2  = dbg.get('t2')
                od  = dbg.get('open_date_raw') or '无'
                ed  = dbg.get('expire_date_raw') or '无退市'
                lt  = dbg.get('latest_trading') or '无'
                ts  = r.get('tail_start') or '无'
                print(f"      {'─'*56}")
                print(f"      [后缺失判断明细]")
                print(f"        open_date（上市日）  : {od}")
                print(f"        expire_date（退市日）: {ed}")
                print(f"        latest_trading      : {lt}")
                print(f"        T2 = min(expire_date, latest_trading) = {t2 or '无'}")
                print(f"        cache_end           : {r['cache_end']}")
                print(f"        后缺失区间          : ({r['cache_end']}, {t2}]  共 {r['tail_missing']} 个交易日")
                print(f"        补充起始日（tail_start）: {ts}")
                print(f"      {'─'*56}")
        if len(tail_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(tail_list)} 只）")

    # 中间缺口
    gap_list = [r for r in results_list if r['has_cache'] and len(r.get('gap_segments', [])) > 0]
    if gap_list:
        print(f"\n  🟡 中间缺口（{len(gap_list)} 只）：")
        for r in gap_list[:MAX_SHOW]:
            dbg  = r.get('_debug', {})
            segs = r.get('gap_segments', [])
            if show_detail:
                segs_str = ', '.join(f"{s}~{e}" for s, e in segs[:3])
                if len(segs) > 3:
                    segs_str += f" ...（共{len(segs)}段）"
                print(f"    {r['symbol']:<16}  {len(segs)} 个缺口段  {segs_str}")
            else:
                print(f"    {r['symbol']:<16}  {len(segs)} 个缺口段")
            if show_verbose:
                cs     = r.get('cache_start') or '无'
                ce     = r.get('cache_end')   or '无'
                od     = dbg.get('open_date_raw')   or '无'
                ed     = dbg.get('expire_date_raw') or '无退市'
                t1     = dbg.get('t1')               or '无'
                t2     = dbg.get('t2')               or '无'
                cs_dbg = dbg.get('calendar_start')   or '无'
                lt     = dbg.get('latest_trading')   or '无'
                counts = dbg.get('gap_segment_counts', [])
                print(f"      {'─'*56}")
                print(f"      [中间缺口判断明细]")
                print(f"        open_date（上市日）  : {od}")
                print(f"        expire_date（退市日）: {ed}")
                print(f"        calendar_start      : {cs_dbg}")
                print(f"        latest_trading      : {lt}")
                print(f"        T1 = max(open_date, calendar_start) = {t1}")
                print(f"        T2 = min(expire_date, latest_trading) = {t2}")
                print(f"        扫描区间（cache）    : [{cs}, {ce}]")
                print(f"        缺口段总数          : {len(segs)} 段")
                for i, (gs, ge) in enumerate(segs, 1):
                    cnt_str = f"  共 {counts[i-1]} 个交易日" if i - 1 < len(counts) else ""
                    print(f"        缺口段 {i:>3}          : {gs} ~ {ge}{cnt_str}")
                print(f"      {'─'*56}")
        if len(gap_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(gap_list)} 只）")

    # 日期异常
    anomaly_list = [r for r in results_list if r.get('date_anomaly', False)]
    if anomaly_list:
        print(f"\n  🔴 日期异常（{len(anomaly_list)} 只）：")
        for r in anomaly_list[:MAX_SHOW]:
            if show_detail:
                print(
                    f"    {r['symbol']:<16}  异常行数：{r.get('anomaly_count', 0)}  "
                    f"最早异常日期：{r.get('anomaly_min_date', '?')}"
                )
            else:
                print(
                    f"    {r['symbol']:<16}  {r.get('anomaly_count', 0)} 行  "
                    f"最早：{r.get('anomaly_min_date', '?')}"
                )
            if show_verbose:
                _sym = r['symbol']
                _period_v = period
                try:
                    import pandas as pd
                    from data_manager.storage import get_default_storage
                    _storage = get_default_storage()
                    _fp = _storage._get_file_path(_sym, _period_v)
                    if _fp.exists():
                        _df = pd.read_parquet(_fp, engine='pyarrow')
                        if not isinstance(_df.index, pd.DatetimeIndex):
                            _df.index = pd.to_datetime(_df.index, errors='coerce')
                        if _df.index.tz is not None:
                            _df.index = _df.index.tz_localize(None)
                        _threshold = pd.Timestamp('1990-12-19')
                        _anomaly_idx = _df.index[_df.index < _threshold]
                        if not _anomaly_idx.empty:
                            _date_counts = {}
                            for _ts in _anomaly_idx:
                                _d = str(_ts.date())
                                _date_counts[_d] = _date_counts.get(_d, 0) + 1
                            print(f"      {'─'*56}")
                            print(f"      [日期异常分布明细]")
                            print(f"        异常行总数          : {len(_anomaly_idx)}")
                            print(f"        最早异常日期        : {r.get('anomaly_min_date', '?')}")
                            print(f"        异常日期分布（前10）:")
                            for _d, _cnt in sorted(_date_counts.items())[:10]:
                                print(f"          {_d}  {_cnt} 行")
                            if len(_date_counts) > 10:
                                print(f"          ...（共 {len(_date_counts)} 个不同异常日期）")
                            print(f"      {'─'*56}")
                except Exception:
                    pass
        if len(anomaly_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(anomaly_list)} 只）")

    # 上市日期缺失
    no_open_date_list = [r for r in results_list if r.get('no_open_date', False)]
    if no_open_date_list:
        print(f"\n  ⚠️  上市日期缺失（{len(no_open_date_list)} 只）：")
        for r in no_open_date_list[:MAX_SHOW]:
            if show_detail:
                _row_count = '?'
                try:
                    from data_manager.storage import get_default_storage as _get_st
                    import pandas as _pd
                    _fp = _get_st()._get_file_path(r['symbol'], period)
                    if _fp.exists():
                        _df = _pd.read_parquet(_fp, engine='pyarrow')
                        _row_count = len(_df)
                except Exception:
                    pass
                print(
                    f"    {r['symbol']:<16}  缓存起始：{r.get('cache_start', '?')}  "
                    f"缓存结束：{r.get('cache_end', '?')}  行数：{_row_count}"
                )
            else:
                print(
                    f"    {r['symbol']:<16}  缓存起始：{r.get('cache_start', '?')}  "
                    f"缓存结束：{r.get('cache_end', '?')}"
                )
            if show_verbose:
                dbg = r.get('_debug', {})
                print(f"      {'─'*56}")
                print(f"      [上市日期缺失判断明细]")
                print(f"        open_date（上市日期）: 无（合约信息中缺失）")
                print(f"        T1 fallback          : 已跳过（不使用 calendar_start 作为基线）")
                print(f"        前缺失检测           : 已跳过（结果不可信）")
                print(f"        后缺失检测           : 正常执行（T2 = {dbg.get('t2', '无')}）")
                print(f"        中间缺口检测         : 正常执行")
                print(f"        cache_start          : {r.get('cache_start', '无')}")
                print(f"        cache_end            : {r.get('cache_end', '无')}")
                print(f"      {'─'*56}")
        if len(no_open_date_list) > MAX_SHOW:
            _warn(f"  （仅显示前 {MAX_SHOW} 只，共 {len(no_open_date_list)} 只）")

    # ── 修复建议 ───────────────────────────────────────────────
    print()
    has_no_cache   = cnt_no_cache > 0
    has_head       = cnt_head > 0
    has_tail       = cnt_tail > 0
    has_gap        = cnt_gap > 0
    has_data_issue = cnt_field > 0 or cnt_type > 0
    problem_types  = sum([has_no_cache, has_head, has_tail, has_gap])

    # 生成修复命令中的来源参数（--sector 或 --symbols）
    _sector_arg = getattr(args, 'sector', None)
    _symbols_arg = getattr(args, 'symbols', None)
    if _sector_arg:
        _src_param = f"--sector {_sector_arg}"
    else:
        _src_param = f"--symbols {_symbols_arg}"

    if problem_types >= 2:
        _warn("修复建议：存在多种数据问题，推荐使用 smart 模式一键修复")
        _info("  ① 修复 miniQMT 本地缓存（先下载缺失数据到 miniQMT）：")
        _info(f"    python dm_cli.py download --asset stock --sub kline "
              f"{_src_param} --period {period} --mode smart")
        _info("  ② 修复 Parquet 缓存（将 miniQMT 数据精准写入 Parquet）：")
        _info(f"    python dm_cli.py sync --asset stock --sub kline "
              f"{_src_param} --period {period} --mode smart")
        _info("  建议先执行 ①，再执行 ②，完成全链路数据修复")
    elif has_no_cache:
        _warn("修复建议：存在无缓存标的，推荐使用 full 模式全量补充")
        _info(f"  python dm_cli.py download --asset stock --sub kline "
              f"{_src_param} --period {period} --mode full --start 20200101")
    elif has_head or has_gap:
        _warn("修复建议：存在前缺失/中间缺口，推荐使用 gap 模式精准补充")
        _info(f"  python dm_cli.py download --asset stock --sub kline "
              f"{_src_param} --period {period} --mode gap")
    elif has_tail:
        _warn("修复建议：存在后缺失，推荐使用 incremental 模式增量补充")
        _info(f"  python dm_cli.py download --asset stock --sub kline "
              f"{_src_param} --period {period} --mode incremental")
        _info("  或使用 sync smart 精准同步 Parquet 缓存：")
        _info(f"    python dm_cli.py sync --asset stock --sub kline "
              f"{_src_param} --period {period} --mode smart")

    if has_data_issue:
        _warn("修复建议：字段/类型异常通常由数据损坏引起，建议重新同步该股票数据")
        _info("  python dm_cli.py sync --asset stock --sub kline "
              f"{_src_param} --period {period}")

    if cnt_anomaly > 0:
        _warn("修复建议：存在日期异常数据（早于 A 股开市日 1990-12-19），建议执行精准清理")
        _info(f"  python dm_cli.py clear --date-anomaly {_src_param} --period {period}")
        _info("  （仅删除异常行，保留正常数据）")

    if cnt_no_open_date > 0:
        _warn("修复建议：存在上市日期缺失的标的，其前缺失检测结果不可信，建议删除缓存后重新同步")
        _info(f"  python dm_cli.py clear --no-open-date {_src_param} --period {period}")
        _info("  （删除整个缓存文件，重新同步后可获得准确数据）")
