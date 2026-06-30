# -*- coding: utf-8 -*-
"""
dm_cli/cmd_download.py — download 与 scan-gaps 子命令实现

包含：cmd_download、_cmd_download_instrument、_cmd_download_calendar、cmd_scan_gaps
"""

import sys

from dm_cli.common import (
    _ok, _warn, _err, _info, _header, _load_service,
    _resolve_symbols, _resolve_sector, _parse_periods,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
    CliCallbacks,
)


# ──────────────────────────────────────────────────────────────────
# 辅助：stock/instrument 下载
# ──────────────────────────────────────────────────────────────────

def _cmd_download_instrument(args):
    """stock/instrument 合约基础信息下载（全量刷新）"""
    from data_manager.download_handlers import InstrumentDownloadHandler

    mode = getattr(args, 'mode', 'full') or 'full'
    if mode not in ('full', ''):
        _warn(f"stock/instrument 只支持全量刷新，忽略 --mode {mode}，以 full 模式执行")

    service = _load_service()

    # ── 解析 symbol 列表 ───────────────────────────────────────
    if getattr(args, 'sector', None):
        symbol_list = _resolve_sector(service, args.sector)
        _header(f"📥 下载合约基础信息（板块：{args.sector}，{len(symbol_list)} 只）")
    else:
        try:
            from data_manager.aux_data import load_instrument_detail
            cached = load_instrument_detail()
            if cached:
                symbol_list = sorted(cached.keys())
                _header(f"📥 下载合约基础信息（使用已缓存合约列表，{len(symbol_list)} 只）")
            else:
                _header("📥 下载合约基础信息")
                _warn("本地无合约缓存，无法确定标的列表")
                _info("请使用 --sector 指定板块名称，例如：--sector 沪深A股")
                sys.exit(1)
        except Exception as e:
            _err(f"读取本地合约缓存失败：{e}")
            sys.exit(1)

    _info(f"品类：stock/instrument")
    _info(f"模式：全量刷新")
    print()

    cb = CliCallbacks(show_progress=True)
    handler = InstrumentDownloadHandler()
    result = handler.execute_batch(
        symbol_list=symbol_list,
        period='',
        start=None,
        end=None,
        mode='full',
        callbacks=cb,
    )
    print()

    if result.get('success'):
        _ok(f"✅ 合约基础信息下载完成，共写入 {result.get('count', 0)} 只")
    else:
        _warn(f"合约基础信息下载失败：{result.get('message', '未知错误')}")


# ──────────────────────────────────────────────────────────────────
# 辅助：stock/calendar 下载
# ──────────────────────────────────────────────────────────────────

def _cmd_download_calendar(args):
    """stock/calendar 交易日历下载（全量刷新）"""
    from data_manager.download_handlers import CalendarDownloadHandler

    mode = getattr(args, 'mode', 'full') or 'full'
    if mode not in ('full', ''):
        _warn(f"stock/calendar 只支持全量刷新，忽略 --mode {mode}，以 full 模式执行")

    _header("📥 下载交易日历（stock/calendar）")
    _info("品类：stock/calendar")
    _info("模式：全量刷新")
    print()

    cb = CliCallbacks(show_progress=True)
    handler = CalendarDownloadHandler()
    result = handler.execute_batch(
        symbol_list=[],
        period='',
        start=None,
        end=None,
        mode='full',
        callbacks=cb,
    )
    print()

    if result.get('success'):
        _ok(f"✅ 交易日历下载完成，共写入 {result.get('count', 0)} 个交易日")
    else:
        _warn(f"交易日历下载失败：{result.get('message', '未知错误')}")


# ──────────────────────────────────────────────────────────────────
# 辅助：index/instrument 下载
# ──────────────────────────────────────────────────────────────────

def _cmd_download_index_instrument(args):
    """index/instrument 指数基础信息下载（全量刷新）"""
    sector = getattr(args, 'sector', None) or '沪深指数'

    mode = getattr(args, 'mode', 'full') or 'full'
    if mode not in ('full', ''):
        _warn(f"index/instrument 只支持全量刷新，忽略 --mode {mode}，以 full 模式执行")

    _header(f"📥 下载指数基础信息（index/instrument，板块：{sector}）")
    _info("品类：index/instrument")
    _info(f"板块：{sector}")
    _info("模式：全量刷新")
    print()

    service = _load_service()
    cb = CliCallbacks(show_progress=True)
    result = service.sync_index_instrument(sector=sector, callbacks=cb)
    print()

    if result.get('success'):
        _ok(f"✅ 指数基础信息下载完成，共写入 {result.get('count', 0)} 只")
    else:
        _warn(f"指数基础信息下载失败：{result.get('message', '未知错误')}")


# ──────────────────────────────────────────────────────────────────
# 主命令入口：download
# ──────────────────────────────────────────────────────────────────

def cmd_download(args):
    """数据下载（全量 / 增量 / 缺口 / 智能）"""
    # ── 解析 --asset / --sub，默认 stock/kline ─────────────────
    asset = (getattr(args, 'asset', None) or 'stock').strip()
    sub   = (getattr(args, 'sub',   None) or 'kline').strip()

    # ── stock/instrument 分支 ──────────────────────────────────
    if asset == 'stock' and sub == 'instrument':
        _cmd_download_instrument(args)
        return

    # ── stock/calendar 分支 ────────────────────────────────────
    if asset == 'stock' and sub == 'calendar':
        _cmd_download_calendar(args)
        return

    # ── index/instrument 分支 ─────────────────────────────────
    if asset == 'index' and sub == 'instrument':
        _cmd_download_index_instrument(args)
        return

    # ── 其他未实现品类（非 stock/kline 且非 index/kline）────────
    if not ((asset == 'stock' and sub == 'kline') or (asset == 'index' and sub == 'kline')):
        _warn(f"download 暂未实现 {asset}/{sub} 的下载逻辑，跳过")
        _info("当前支持：stock/kline、stock/instrument、stock/calendar、index/kline、index/instrument")
        sys.exit(0)

    # ── 校验 kline 必填参数 ────────────────────────────────────
    if not getattr(args, 'period', None):
        _err(f"下载 {asset}/kline 数据需要 --period 参数（数据周期，如 1d,1m）")
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
    periods = _parse_periods(args.period)
    mode = getattr(args, 'mode', 'incremental') or 'incremental'

    _MODE_LABELS = {
        'full':        '全量',
        'incremental': '增量',
        'gap':         '缺口',
        'smart':       '智能',
    }
    mode_label = _MODE_LABELS.get(mode, mode)

    _header(f"📥 数据下载（{mode_label}）")
    _info(f"品类：{asset}/{sub}")
    _info(source_label)
    _info(f"周期：{', '.join(periods)}")

    start_date = getattr(args, 'start', None) or ''
    end_date = getattr(args, 'end', None) or ''
    yes_flag = getattr(args, 'yes', False)

    if mode == 'full':
        if not start_date:
            _err("全量模式（--mode full）必须指定 --start 起始日期")
            sys.exit(1)
        _info(f"日期：{start_date} ~ {end_date or '最新'}")
    elif mode == 'incremental':
        _info("模式：增量（从 miniQMT 本地最后一条往后补充）")
    elif mode == 'gap':
        _info("模式：缺口（扫描 Parquet 缓存缺口后精准补充）")
    elif mode == 'smart':
        _info("模式：智能（自动 validate → 分层 → 精准下载）")
    print()

    stop_flag_val = [False]

    def _stop_flag():
        return stop_flag_val[0]

    # ── smart 模式：validate → 分层 → 下载 ────────────────────
    if mode == 'smart':
        try:
            from data_manager.asset_types import get_asset_type
        except ImportError as e:
            _err(f"无法导入 asset_types 模块：{e}")
            sys.exit(1)

        at_config = get_asset_type(asset)
        sub_config = at_config.get_sub_type(sub) if at_config else None
        if sub_config is None:
            _err(f"未找到品类配置：{asset}/{sub}")
            sys.exit(1)

        strategy = getattr(sub_config, 'download_strategy', [])
        if not strategy:
            _warn(f"该子类（{asset}/{sub}）暂不支持 smart 下载")
            sys.exit(0)

        for period in periods:
            _info(f"── 开始智能下载 {period} 数据 ──")

            # Step 1：执行 validate 扫描
            _info("Step 1/3：执行数据健康检查...")
            cb_validate = CliCallbacks(show_progress=True)
            try:
                validate_result = service.validate_kline(
                    params={
                        'stock_list':      symbols,
                        'period':          period,
                        'sub_type_config': sub_config,
                    },
                    callbacks=cb_validate,
                    stop_flag=_stop_flag,
                )
            except KeyboardInterrupt:
                stop_flag_val[0] = True
                print()
                _warn("已被用户中断（Ctrl+C）")
                return

            print()
            if not validate_result.get('success') and not validate_result.get('interrupted'):
                _err("validate 扫描失败，无法继续")
                continue

            cnt_no_cache   = validate_result.get('no_cache', 0)
            cnt_head       = validate_result.get('head_missing', 0)
            cnt_tail       = validate_result.get('tail_missing', 0)
            cnt_gap        = validate_result.get('gap', 0)
            cnt_healthy    = validate_result.get('healthy', 0)
            total_scanned  = validate_result.get('total', 0)

            _info(f"健康检查结果：总计 {total_scanned} | 健康 {cnt_healthy} | "
                  f"无缓存 {cnt_no_cache} | 前缺失 {cnt_head} | 后缺失 {cnt_tail} | 中间缺口 {cnt_gap}")

            if cnt_no_cache == 0 and cnt_head == 0 and cnt_tail == 0 and cnt_gap == 0:
                _ok("✅ 数据健康，无需下载")
                continue

            # Step 2：生成下载计划并展示
            _info("\nStep 2/3：生成下载计划...")
            try:
                from data_manager.download_handlers import build_download_plan
                plan = build_download_plan(
                    validate_results=validate_result.get('results', []),
                    period=period,
                    sub_type_config=sub_config,
                    default_start=start_date or None,
                )
            except Exception as e:
                _err(f"生成下载计划失败：{e}")
                continue

            print()
            print(plan.summary())
            print()

            if plan.total_batches == 0:
                _ok("✅ 数据健康，无需下载")
                continue

            # Step 3：用户确认
            if not yes_flag:
                try:
                    confirm = input("  确认执行下载？[y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    _warn("已取消")
                    return
                if confirm != 'y':
                    _warn("已取消")
                    continue

            # Step 4：执行下载
            _info("Step 3/3：执行下载...")
            cb_smart = CliCallbacks(show_progress=True)
            try:
                result = service.smart_download(
                    validate_result=validate_result,
                    params={
                        'asset_type':    asset,
                        'sub_type':      sub,
                        'period':        period,
                        'default_start': start_date or None,
                    },
                    callbacks=cb_smart,
                    stop_flag=_stop_flag,
                )
            except KeyboardInterrupt:
                stop_flag_val[0] = True
                print()
                _warn("已被用户中断（Ctrl+C）")
                return

            print()
            if result.get('interrupted'):
                _warn("下载已中断")
            elif result.get('success'):
                _ok(f"✅ 智能下载完成 | 下载标的：{result.get('download_count', 0)} 只 | "
                    f"成功批次：{result.get('done_batches', 0) - result.get('failed_batches', 0)} | "
                    f"失败批次：{result.get('failed_batches', 0)}")
            else:
                _warn(f"下载完成（有失败批次）| 失败：{result.get('failed_batches', 0)} 批次")
        return

    # ── 普通模式（full / incremental / gap）───────────────────
    for period in periods:
        _info(f"── 开始{mode_label}下载 {period} 数据 ──")
        cb = CliCallbacks(show_progress=True)
        batch_size = getattr(args, 'batch_size', 0) or 0
        try:
            result = service.download(
                params={
                    'stock_list': symbols,
                    'period_type': period,
                    'mode': mode,
                    'start_date': start_date,
                    'end_date': end_date,
                    'batch_size': batch_size,
                },
                callbacks=cb,
                stop_flag=_stop_flag,
            )
        except KeyboardInterrupt:
            stop_flag_val[0] = True
            print()
            _warn("已被用户中断（Ctrl+C）")
            return

        print()
        if result.get('interrupted'):
            _warn(result['message'])
        elif result.get('success'):
            _ok(result['message'])
        else:
            _err(result['message'])


# ──────────────────────────────────────────────────────────────────
# 主命令入口：scan-gaps
# ──────────────────────────────────────────────────────────────────

def cmd_scan_gaps(args):
    """扫描板块数据缺口（只检测，不下载）"""
    # ── 解析 --asset / --sub，默认 stock/kline ─────────────────
    asset = (getattr(args, 'asset', None) or 'stock').strip()
    sub   = (getattr(args, 'sub',   None) or 'kline').strip()

    if asset != 'stock' or sub != 'kline':
        _warn(f"scan-gaps 暂未实现 {asset}/{sub} 的缺口扫描逻辑，跳过")
        _info("当前支持：stock/kline")
        sys.exit(0)

    # ── 校验 kline 必填参数 ────────────────────────────────────
    if not getattr(args, 'sector', None):
        _err("扫描 stock/kline 缺口需要 --sector 参数（板块名称）")
        sys.exit(1)
    if not getattr(args, 'period', None):
        _err("扫描 stock/kline 缺口需要 --period 参数（数据周期，如 1d,1m）")
        sys.exit(1)

    service = _load_service()
    symbols = _resolve_sector(service, args.sector)
    periods = _parse_periods(args.period)

    _header(f"🔍 扫描数据缺口")
    _info(f"品类：{asset}/{sub}")
    _info(f"板块：{args.sector}（{len(symbols)} 只）")
    _info(f"周期：{', '.join(periods)}")
    print()

    try:
        from data_manager.data_integrity import batch_scan_gaps
    except ImportError as e:
        _err(f"无法导入 data_integrity 模块：{e}")
        sys.exit(1)

    # 获取交易日历
    _info("正在获取交易日历...")
    try:
        trading_dates = service._fetch_trading_dates_sorted()
        _info(f"交易日历加载完成，共 {len(trading_dates)} 个交易日")
    except Exception as e:
        _err(f"获取交易日历失败：{e}")
        sys.exit(1)

    for period in periods:
        _info(f"\n── 扫描 {period} 数据缺口 ──")

        total_scanned = 0
        total_has_gap = 0
        total_no_cache = 0
        total_segments = 0

        def _on_progress(done, total):
            if total > 0 and (done % max(1, total // 20) == 0 or done == total):
                print(f"\r  扫描进度：{done}/{total}", end="", flush=True)

        results = batch_scan_gaps(
            symbol_list=symbols,
            period=period,
            trading_dates_sorted=trading_dates,
            on_progress=_on_progress,
        )
        print()  # 换行

        gap_symbols = []
        for symbol, info in results.items():
            total_scanned += 1
            if not info['has_cache']:
                total_no_cache += 1
            elif info['gap_count'] > 0:
                total_has_gap += 1
                total_segments += info['gap_count']
                gap_symbols.append((symbol, info['gap_count'], info['segments']))

        print(f"\n  扫描结果（{period}）：")
        print(f"    总扫描：{total_scanned} 只")
        print(f"    无缓存：{total_no_cache} 只（请先执行数据同步）")
        print(f"    有缺口：{total_has_gap} 只，共 {total_segments} 个缺口段")
        print(f"    无缺口：{total_scanned - total_no_cache - total_has_gap} 只")

        if gap_symbols and args.detail:
            print(f"\n  缺口明细：")
            for symbol, gap_count, segments in gap_symbols[:50]:
                segs_str = ', '.join(
                    f"{s}~{e}" if s != e else s for s, e in segments[:3]
                )
                if len(segments) > 3:
                    segs_str += f" ...（共{gap_count}段）"
                print(f"    {symbol:<16} {gap_count:>3} 段  {segs_str}")
            if len(gap_symbols) > 50:
                _warn(f"  （仅显示前 50 只，共 {len(gap_symbols)} 只有缺口）")

        if total_has_gap > 0:
            _warn(f"发现 {total_has_gap} 只股票有数据缺口，可运行 download --mode gap 命令下载")
        else:
            _ok(f"所有已缓存股票的 {period} 数据完整，无缺口")
