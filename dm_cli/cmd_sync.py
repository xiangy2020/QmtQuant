# -*- coding: utf-8 -*-
"""
dm_cli/cmd_sync.py — sync 子命令实现

包含：cmd_sync、_sync_list_categories、_sync_kline、_sync_stock_aux、_sync_industry
"""

import sys

from dm_cli.common import (
    _ok, _warn, _err, _info, _header, _load_service,
    _resolve_symbols, _resolve_sector, _parse_periods,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
    CliCallbacks,
)


def _sync_list_categories():
    """展示已启用品类体系表格（--list 功能）"""
    from data_manager.asset_types import ENABLED_ASSET_TYPES
    _header("📋 已启用品类体系")
    print()
    col_asset = 12
    col_sub   = 16
    col_name  = 14
    col_desc  = 30
    header = (
        f"  {'一级品类':<{col_asset}}{'子类':<{col_sub}}"
        f"{'显示名称':<{col_name}}{'描述'}"
    )
    sep = f"  {'─'*col_asset}{'─'*col_sub}{'─'*col_name}{'─'*col_desc}"
    print(header)
    print(sep)
    for at in ENABLED_ASSET_TYPES:
        for i, st in enumerate(at.sub_types):
            asset_col = at.asset_type if i == 0 else ''
            print(
                f"  {_CYAN}{asset_col:<{col_asset}}{_RESET}"
                f"{st.sub_type:<{col_sub}}"
                f"{st.display_name:<{col_name}}"
                f"{st.description}"
            )
        print(sep)
    print()


def _sync_kline(service, args):
    """同步 stock/kline 子类"""
    # 校验必要参数
    if not args.period:
        _err("同步 kline 子类需要 --period 参数（数据周期，如 1d,1m）")
        sys.exit(1)

    symbols, source_label = _resolve_symbols(args, service)
    periods = _parse_periods(args.period)
    mode = getattr(args, 'mode', 'full') or 'full'

    # ── smart 模式：先 validate 再精准同步 ────────────────────
    if mode == 'smart':
        _header("🔄 智能同步 stock/kline（K线行情）")
        _info(source_label)
        _info(f"周期：{', '.join(periods)}")
        _info("模式：智能（先 validate 扫描 Parquet 缓存，再精准同步缺失部分）")
        print()

        yes_flag = getattr(args, 'yes', False)
        stop_flag_val = [False]

        def _stop_flag():
            return stop_flag_val[0]

        # 获取 SubTypeConfig
        try:
            from data_manager.asset_types import get_asset_type
            at_cfg = get_asset_type('stock')
            sub_cfg = at_cfg.get_sub_type('kline')
        except Exception as e:
            _err(f"无法加载 SubTypeConfig：{e}")
            sys.exit(1)

        for period in periods:
            _info(f"── 周期 {period} ──")

            # Step 1：validate 扫描
            _info("Step 1/3：执行 validate 健康检查...")

            def _on_progress(done, total):
                if total > 0 and (done % max(1, total // 20) == 0 or done == total):
                    print(f"\r  校验进度：{done}/{total}", end="", flush=True)

            cb_val = CliCallbacks(show_progress=False)
            cb_val.on_progress = _on_progress

            try:
                validate_result = service.validate_kline(
                    params={
                        'stock_list':      symbols,
                        'period':          period,
                        'sub_type_config': sub_cfg,
                    },
                    callbacks=cb_val,
                    stop_flag=_stop_flag,
                )
            except KeyboardInterrupt:
                stop_flag_val[0] = True
                print()
                _warn("已被用户中断（Ctrl+C）")
                return

            print()  # 换行

            # 输出 validate 汇总
            total_cnt    = validate_result.get('total', 0)
            cnt_no_cache = validate_result.get('no_cache', 0)
            cnt_head     = validate_result.get('head_missing', 0)
            cnt_tail     = validate_result.get('tail_missing', 0)
            cnt_gap      = validate_result.get('gap', 0)
            cnt_healthy  = validate_result.get('healthy', 0)
            print(f"\n  校验汇总（{period}）：")
            print(f"    总扫描：{total_cnt} 只")
            print(f"    ✅ 完全健康：{cnt_healthy} 只")
            print(f"    ⬜ 无缓存：{cnt_no_cache} 只")
            print(f"    🟡 前缺失：{cnt_head} 只")
            print(f"    🟡 后缺失：{cnt_tail} 只")
            print(f"    🟡 中间缺口：{cnt_gap} 只")
            print()

            # Step 2：生成同步计划
            _info("Step 2/3：生成同步计划...")
            from data_manager.download_handlers import build_download_plan
            plan = build_download_plan(
                validate_results=validate_result.get('results', []),
                period=period,
                sub_type_config=sub_cfg,
                default_start=getattr(args, 'start', None) or None,
            )
            print()
            print(plan.summary())
            print()

            if plan.total_batches == 0:
                _ok("✅ Parquet 缓存健康，无需同步")
                continue

            # 用户确认
            if not yes_flag:
                try:
                    confirm = input("  确认执行同步？[y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    _warn("已取消")
                    return
                if confirm != 'y':
                    _warn("已取消")
                    continue

            # Step 3：执行精准同步
            _info("Step 3/3：执行精准同步...")
            cb_smart = CliCallbacks(show_progress=True)
            try:
                result = service.sync_smart(
                    validate_result=validate_result,
                    params={
                        'period':        period,
                        'default_start': getattr(args, 'start', None) or None,
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
                _warn("同步已中断")
            elif result.get('success'):
                _ok(f"✅ 智能同步完成 | 同步标的：{result.get('sync_count', 0)} 只 | "
                    f"成功批次：{result.get('done_batches', 0) - result.get('failed_batches', 0)} | "
                    f"失败批次：{result.get('failed_batches', 0)}")
            else:
                _warn(f"同步完成（有失败批次）| 失败：{result.get('failed_batches', 0)} 批次")
        return

    # ── full 模式（默认）：全量覆盖写 ─────────────────────────
    start_date = args.start or '19900101'
    end_date = args.end or ''

    _header("🔄 同步 stock/kline（K线行情）")
    _info(source_label)
    _info(f"周期：{', '.join(periods)}")
    _info(f"日期：{start_date} ~ {end_date or '最新'}")
    print()

    cb = CliCallbacks(show_progress=True)
    result = service.sync(
        params={
            'symbols': symbols,
            'periods': periods,
            'start_date': start_date,
            'end_date': end_date,
            'batch_size': getattr(args, 'batch_size', 0) or 0,
        },
        callbacks=cb,
    )
    print()
    _ok(
        f"同步完成 | 成功：{result.get('success', 0)} | "
        f"失败：{result.get('failed', 0)} | "
        f"跳过：{result.get('skipped', 0)} | "
        f"耗时：{result.get('elapsed', 0)}s"
    )


def _sync_stock_aux(service, args, sub_types_to_sync):
    """同步 stock/calendar 和/或 stock/instrument 子类"""
    need_calendar   = 'calendar'   in sub_types_to_sync
    need_instrument = 'instrument' in sub_types_to_sync

    symbol_list = None
    if need_instrument:
        if args.sector:
            symbol_list = _resolve_sector(service, args.sector)
            _header(f"📅 同步辅助数据（板块：{args.sector}，{len(symbol_list)} 只）")
        else:
            try:
                from data_manager.aux_data import load_instrument_detail
                cached = load_instrument_detail()
                if cached:
                    symbol_list = sorted(cached.keys())
                    _header(f"📅 同步辅助数据（使用已缓存合约列表，{len(symbol_list)} 只）")
                else:
                    _header("📅 同步辅助数据（仅交易日历，本地无合约缓存）")
                    _info("提示：如需同步合约信息，请使用 --sector 指定板块名称")
            except Exception as e:
                _warn(f"读取本地合约缓存失败（{e}），将仅同步交易日历")
    else:
        _header("📅 同步 stock/calendar（交易日历）")

    sub_desc = []
    if need_calendar:
        sub_desc.append('calendar')
    if need_instrument:
        sub_desc.append('instrument')
    _info(f"同步子类：{', '.join(sub_desc)}")
    print()

    cb = CliCallbacks(show_progress=True)
    result = service.sync_aux_data(symbol_list=symbol_list if need_instrument else None, callbacks=cb)
    print()

    if need_calendar:
        if result.get('calendar_ok'):
            _ok("交易日历（calendar）同步完成")
        else:
            _warn("交易日历（calendar）同步失败或跳过")

    if need_instrument and symbol_list:
        if result.get('detail_ok'):
            _ok(f"合约基础信息（instrument）同步完成，共 {result.get('detail_count', 0)} 只")
        else:
            _warn("合约基础信息（instrument）同步失败或跳过")


def _sync_industry(service, args, sub_types_to_sync):
    """同步 industry/sector_list 和/或 industry/members 子类"""
    need_sector_list = 'sector_list' in sub_types_to_sync
    need_members     = 'members'     in sub_types_to_sync

    sectors = None
    if getattr(args, 'sectors', None):
        sectors = [s.strip() for s in args.sectors.split(',') if s.strip()]

    sub_desc = []
    if need_sector_list:
        sub_desc.append('sector_list')
    if need_members:
        sub_desc.append('members')

    if sectors:
        _header(f"🏭 同步行业概念数据（指定板块：{len(sectors)} 个）")
        _info(f"指定板块：{', '.join(sectors)}")
    else:
        _header(f"🏭 同步行业概念数据（全量）")
    _info(f"同步子类：{', '.join(sub_desc)}")
    print()

    stop_flag_val = [False]

    def _stop_flag():
        return stop_flag_val[0]

    params = {}
    if sectors:
        params['sectors'] = sectors

    cb = CliCallbacks(show_progress=True)
    try:
        result = service.sync_industry_data(
            params=params,
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
        _warn(
            f"同步已中断 | 板块总数：{result.get('total_sectors', 0)} | "
            f"成功：{result.get('members_success', 0)} | "
            f"失败：{result.get('members_failed', 0)}"
        )
    elif result.get('success'):
        _ok(
            f"同步完成 | 板块总数：{result.get('total_sectors', 0)} | "
            f"成功：{result.get('members_success', 0)} | "
            f"失败：{result.get('members_failed', 0)}"
        )
        if need_sector_list:
            if result.get('sector_list_ok'):
                _ok("板块分类信息（sector_list）已同步")
            else:
                _warn("板块分类信息（sector_list）同步失败")
    else:
        _err(
            f"同步失败 | 板块总数：{result.get('total_sectors', 0)} | "
            f"成功：{result.get('members_success', 0)} | "
            f"失败：{result.get('members_failed', 0)}"
        )


def _sync_index(service, args, subs_to_sync):
    """同步 index 品类（instrument / kline）"""
    need_instrument = 'instrument' in subs_to_sync
    need_kline      = 'kline'      in subs_to_sync

    # ── index/instrument：指数基础信息 ────────────────────────
    if need_instrument:
        sector = getattr(args, 'sector', None) or '沪深指数'
        _header(f"📋 同步指数基础信息（板块：{sector}）")
        _info("品类：index/instrument")
        _info(f"板块：{sector}")
        print()

        cb = CliCallbacks(show_progress=True)
        result = service.sync_index_instrument(sector=sector, callbacks=cb)
        print()
        if result.get('success'):
            _ok(f"指数基础信息（instrument）同步完成，共 {result.get('count', 0)} 只")
        else:
            _warn(f"指数基础信息（instrument）同步失败：{result.get('message', '未知错误')}")

    # ── index/kline：指数 K 线行情 ────────────────────────────
    if need_kline:
        if not getattr(args, 'period', None):
            _err("同步 index/kline 子类需要 --period 参数（数据周期，如 1d,1m）")
            return

        periods = _parse_periods(args.period)
        mode = getattr(args, 'mode', 'full') or 'full'

        # 获取指数代码列表（优先 --symbols，否则用全量缓存）
        from data_manager.aux_data import load_index_instrument_detail
        symbols_arg = getattr(args, 'symbols', None)

        if symbols_arg:
            symbols = [s.strip() for s in symbols_arg.split(',') if s.strip()]
            if not symbols:
                _err("--symbols 不能为空")
                return
            n = len(symbols)
            if n > 5:
                preview = ', '.join(symbols[:3])
                source_label = f"来源：--symbols（{preview} 等 {n} 只）"
            else:
                source_label = f"来源：--symbols（{', '.join(symbols)}，{n} 只）"
        else:
            cached = load_index_instrument_detail()
            if cached:
                symbols = sorted(cached.keys())
                source_label = f"来源：本地指数缓存（{len(symbols)} 只）"
            else:
                _warn("本地无指数缓存，请先执行：python dm_cli.py sync --asset index --sub instrument")
                return

        _header(f"🔄 同步 index/kline（K线行情）")
        _info(source_label)
        _info(f"周期：{', '.join(periods)}")

        if mode == 'smart':
            _info("模式：智能（先 validate 扫描 Parquet 缓存，再精准同步缺失部分）")
            print()

            try:
                from data_manager.asset_types import get_asset_type
                at_cfg = get_asset_type('index')
                sub_cfg = at_cfg.get_sub_type('kline')
            except Exception as e:
                _err(f"无法加载 SubTypeConfig：{e}")
                return

            yes_flag = getattr(args, 'yes', False)
            stop_flag_val = [False]

            def _stop_flag():
                return stop_flag_val[0]

            for period in periods:
                _info(f"── 周期 {period} ──")
                _info("Step 1/3：执行 validate 健康检查...")

                def _on_progress(done, total):
                    if total > 0 and (done % max(1, total // 20) == 0 or done == total):
                        print(f"\r  校验进度：{done}/{total}", end="", flush=True)

                cb_val = CliCallbacks(show_progress=False)
                cb_val.on_progress = _on_progress

                try:
                    validate_result = service.validate_kline(
                        params={
                            'stock_list':      symbols,
                            'period':          period,
                            'sub_type_config': sub_cfg,
                            'asset_type':      'index',
                        },
                        callbacks=cb_val,
                        stop_flag=_stop_flag,
                    )
                except KeyboardInterrupt:
                    stop_flag_val[0] = True
                    print()
                    _warn("已被用户中断（Ctrl+C）")
                    return

                print()
                total_cnt    = validate_result.get('total', 0)
                cnt_no_cache = validate_result.get('no_cache', 0)
                cnt_tail     = validate_result.get('tail_missing', 0)
                cnt_gap      = validate_result.get('gap', 0)
                cnt_healthy  = validate_result.get('healthy', 0)
                print(f"\n  校验汇总（{period}）：")
                print(f"    总扫描：{total_cnt} 只")
                print(f"    ✅ 完全健康：{cnt_healthy} 只")
                print(f"    ⬜ 无缓存：{cnt_no_cache} 只")
                print(f"    🟡 后缺失：{cnt_tail} 只")
                print(f"    🟡 中间缺口：{cnt_gap} 只")
                print()

                _info("Step 2/3：生成同步计划...")
                from data_manager.download_handlers import build_download_plan
                plan = build_download_plan(
                    validate_results=validate_result.get('results', []),
                    period=period,
                    sub_type_config=sub_cfg,
                    default_start=getattr(args, 'start', None) or None,
                )
                print()
                print(plan.summary())
                print()

                if plan.total_batches == 0:
                    _ok("✅ Parquet 缓存健康，无需同步")
                    continue

                if not yes_flag:
                    try:
                        confirm = input("  确认执行同步？[y/N] ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        _warn("已取消")
                        return
                    if confirm != 'y':
                        _warn("已取消")
                        continue

                _info("Step 3/3：执行精准同步...")
                cb_smart = CliCallbacks(show_progress=True)
                try:
                    result = service.sync_smart(
                        validate_result=validate_result,
                        params={
                            'period':        period,
                            'default_start': getattr(args, 'start', None) or None,
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
                    _warn("同步已中断")
                elif result.get('success'):
                    _ok(f"✅ 智能同步完成 | 同步标的：{result.get('sync_count', 0)} 只 | "
                        f"成功批次：{result.get('done_batches', 0) - result.get('failed_batches', 0)} | "
                        f"失败批次：{result.get('failed_batches', 0)}")
                else:
                    _warn(f"同步完成（有失败批次）| 失败：{result.get('failed_batches', 0)} 批次")
            return

        # full 模式（默认）
        start_date = getattr(args, 'start', None) or '19900101'
        end_date   = getattr(args, 'end',   None) or ''
        _info(f"日期：{start_date} ~ {end_date or '最新'}")
        print()

        cb = CliCallbacks(show_progress=True)
        result = service.sync(
            params={
                'symbols':    symbols,
                'periods':    periods,
                'start_date': start_date,
                'end_date':   end_date,
                'asset_type': 'index',
            },
            callbacks=cb,
        )
        print()
        _ok(
            f"同步完成 | 成功：{result.get('success', 0)} | "
            f"失败：{result.get('failed', 0)} | "
            f"跳过：{result.get('skipped', 0)} | "
            f"耗时：{result.get('elapsed', 0)}s"
        )


def cmd_sync(args):
    """统一数据同步入口，支持按一级品类和二级子类灵活选择"""
    from data_manager.asset_types import ENABLED_ASSET_TYPES, get_asset_type

    # ── 解析 --asset（一级品类） ───────────────────────────────
    enabled_ids = {at.asset_type for at in ENABLED_ASSET_TYPES}
    if getattr(args, 'asset', None):
        requested_assets = [a.strip() for a in args.asset.split(',') if a.strip()]
        invalid_assets = [a for a in requested_assets if a not in enabled_ids]
        if invalid_assets:
            _err(f"不存在或未启用的品类：{invalid_assets}")
            _err(f"可用品类：{sorted(enabled_ids)}")
            sys.exit(1)
        target_assets = [get_asset_type(a) for a in requested_assets]
    else:
        target_assets = list(ENABLED_ASSET_TYPES)

    # ── 解析 --sub（二级子类） ─────────────────────────────────
    requested_subs = None
    if getattr(args, 'sub', None):
        requested_subs = {s.strip() for s in args.sub.split(',') if s.strip()}

    # ── 逐品类分发同步 ─────────────────────────────────────────
    service = _load_service()

    for at in target_assets:
        if requested_subs is not None:
            available_subs = {st.sub_type for st in at.sub_types}
            subs_to_sync = requested_subs & available_subs
            skipped = requested_subs - available_subs
            if skipped:
                _warn(f"品类 {at.asset_type} 下不存在子类：{sorted(skipped)}，已跳过")
            if not subs_to_sync:
                _warn(f"品类 {at.asset_type} 下无匹配子类，跳过")
                continue
        else:
            subs_to_sync = {st.sub_type for st in at.sub_types}

        # ── stock 品类分发 ─────────────────────────────────────
        if at.asset_type == 'stock':
            if 'kline' in subs_to_sync:
                _sync_kline(service, args)
            aux_subs = subs_to_sync & {'calendar', 'instrument'}
            if aux_subs:
                _sync_stock_aux(service, args, aux_subs)
            other_subs = subs_to_sync - {'kline', 'calendar', 'instrument'}
            for sub in sorted(other_subs):
                _warn(f"stock/{sub} 暂未实现同步逻辑，跳过")

        # ── industry 品类分发 ──────────────────────────────────
        elif at.asset_type == 'industry':
            industry_subs = subs_to_sync & {'sector_list', 'members'}
            if industry_subs:
                _sync_industry(service, args, industry_subs)
            other_subs = subs_to_sync - {'sector_list', 'members'}
            for sub in sorted(other_subs):
                _warn(f"industry/{sub} 暂未实现同步逻辑，跳过")

        # ── index 品类分发 ─────────────────────────────────────
        elif at.asset_type == 'index':
            index_subs = subs_to_sync & {'instrument', 'kline'}
            if index_subs:
                _sync_index(service, args, index_subs)
            other_subs = subs_to_sync - {'instrument', 'kline'}
            for sub in sorted(other_subs):
                _warn(f"index/{sub} 暂未实现同步逻辑，跳过")

        # ── 其他品类（预留） ───────────────────────────────────
        else:
            _warn(f"品类 {at.asset_type}（{at.display_name}）暂未实现同步逻辑，跳过")
