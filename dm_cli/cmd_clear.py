# -*- coding: utf-8 -*-
"""
dm_cli/cmd_clear.py — clear 子命令实现

包含：cmd_clear 及其所有内部辅助逻辑
"""

import sys

from dm_cli.common import (
    _ok, _warn, _err, _info, _header, _load_service, _resolve_symbols,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
    CliCallbacks,
)


def cmd_clear(args):
    """清空缓存"""
    service = _load_service()

    if args.all:
        _header("🗑  清空全部缓存")
        confirm = input(f"\n  {_YELLOW}警告：此操作将删除所有本地 Parquet 缓存，不可恢复！{_RESET}\n  确认请输入 yes：")
        if confirm.strip().lower() != 'yes':
            _info("已取消")
            return
        result = service.clear_all_cache()
        if result['success']:
            _ok(f"已删除 {result['deleted_files']} 个文件，释放 {result['freed_mb']:.1f} MB")
        else:
            _err(f"清空失败：{result.get('error')}")

    elif args.symbol:
        period_str = f" {args.period}" if args.period else "（所有周期）"
        _header(f"🗑  清除缓存：{args.symbol}{period_str}")
        result = service.clear_symbol_cache(args.symbol, args.period)
        if result['success']:
            if result['deleted_files'] > 0:
                _ok(f"已删除 {result['deleted_files']} 个文件，释放 {result['freed_mb']:.4f} MB")
            else:
                _warn("未找到对应缓存文件")
        else:
            _err(f"清除失败：{result.get('error')}")

    elif getattr(args, 'date_anomaly', False):
        _clear_date_anomaly(args, service)

    elif getattr(args, 'no_open_date', False):
        _clear_no_open_date(args, service)

    else:
        _err("请指定 --all、--symbol、--date-anomaly 或 --no-open-date")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────
# 内部辅助：--date-anomaly 模式
# ──────────────────────────────────────────────────────────────────

def _clear_date_anomaly(args, service):
    """精准行级清理日期异常数据（早于 A 股开市日 1990-12-19）"""
    import pandas as pd
    from data_manager.storage import get_default_storage as _get_storage

    period = getattr(args, 'period', None)
    sector = getattr(args, 'sector', None)
    symbols_arg = getattr(args, 'symbols', None)
    skip_confirm = getattr(args, 'yes', False)

    _header("🗑  精准清理日期异常数据（早于 A 股开市日 1990-12-19）")

    # 解析股票列表
    if symbols_arg:
        symbols = [s.strip() for s in symbols_arg.split(',') if s.strip()]
        _info(f"来源：指定代码（{len(symbols)} 只）")
    elif sector:
        symbols, _ = _resolve_symbols(args, service)
        _info(f"来源：板块 {sector}（{len(symbols)} 只）")
    else:
        _info("来源：全量缓存（未指定 --sector / --symbols）")
        try:
            _storage = _get_storage()
            if period:
                symbols = _storage.list_symbols(period)
            else:
                _all_syms = set()
                for _p in _storage.list_periods():
                    _all_syms.update(_storage.list_symbols(_p))
                symbols = sorted(_all_syms)
        except Exception as _e:
            _err(f"获取全量缓存列表失败：{_e}")
            sys.exit(1)

    if not symbols:
        _warn("未找到任何股票，退出")
        return

    if period:
        _info(f"周期：{period}")
        period_list = [period]
    else:
        try:
            period_list = _get_storage().list_periods()
        except Exception:
            period_list = ['1d']
        _info(f"周期：全部（{', '.join(period_list)}）")

    # ── 预扫描：统计异常情况 ──────────────────────────────────
    _info("正在预扫描异常数据...")
    _storage = _get_storage()
    _threshold = pd.Timestamp('1990-12-19')

    preview_anomaly_symbols = []
    preview_total_rows = 0

    for _sym in symbols:
        for _p in period_list:
            try:
                _fp = _storage._get_file_path(_sym, _p)
                if not _fp.exists():
                    continue
                _df = pd.read_parquet(_fp, engine='pyarrow')
                if _df.empty:
                    continue
                if not isinstance(_df.index, pd.DatetimeIndex):
                    _df.index = pd.to_datetime(_df.index, errors='coerce')
                if _df.index.tz is not None:
                    _df.index = _df.index.tz_localize(None)
                _cnt = int((_df.index < _threshold).sum())
                if _cnt > 0:
                    preview_anomaly_symbols.append((_sym, _p, _cnt))
                    preview_total_rows += _cnt
            except Exception:
                pass

    if not preview_anomaly_symbols:
        _ok(f"扫描完成，未发现日期异常数据（共扫描 {len(symbols)} 只股票）")
        return

    # 展示预览
    print(f"\n  发现 {len(preview_anomaly_symbols)} 只股票存在日期异常，共 {preview_total_rows} 行")
    MAX_PREVIEW = 10
    for _sym, _p, _cnt in preview_anomaly_symbols[:MAX_PREVIEW]:
        print(f"    {_sym:<16}  {_p}  {_cnt} 行")
    if len(preview_anomaly_symbols) > MAX_PREVIEW:
        _warn(f"  （仅显示前 {MAX_PREVIEW} 只，共 {len(preview_anomaly_symbols)} 只）")

    # ── 二次确认 ──────────────────────────────────────────────
    if not skip_confirm:
        confirm = input(
            f"\n  {_YELLOW}将精准删除以上 {preview_total_rows} 行异常数据（保留正常数据），"
            f"此操作不可撤销！{_RESET}\n  确认请输入 yes："
        )
        if confirm.strip().lower() != 'yes':
            _info("已取消")
            return

    # ── 执行清理 ──────────────────────────────────────────────
    print()
    _info("开始清理...")

    total_cleaned = 0
    total_failed = 0
    total_removed_rows = 0
    total_freed_mb = 0.0

    for _p in period_list:
        _syms_for_period = [_sym for _sym, _pp, _ in preview_anomaly_symbols if _pp == _p]
        if not _syms_for_period:
            continue

        result = service.clear_date_anomaly(
            params={'stock_list': _syms_for_period, 'period': _p},
            callbacks=CliCallbacks(show_progress=False),
        )
        print()  # 换行

        total_cleaned += result.get('cleaned', 0)
        total_failed += result.get('failed', 0)
        total_removed_rows += result.get('total_removed_rows', 0)
        total_freed_mb += result.get('freed_mb', 0.0)

        if result.get('errors'):
            for err_item in result['errors']:
                _warn(f"  清理失败：{err_item['symbol']}  {err_item['error']}")

    # ── 输出汇总 ──────────────────────────────────────────────
    print(f"\n  {'─'*50}")
    print(f"  清理汇总：")
    print(f"    扫描总数：{len(symbols)} 只")
    print(f"    发现异常：{len(preview_anomaly_symbols)} 只")
    print(f"    成功清理：{total_cleaned} 只")
    if total_failed > 0:
        print(f"    失败：{total_failed} 只")
    print(f"    共删除行数：{total_removed_rows} 行")
    print(f"    释放空间：{total_freed_mb:.4f} MB")
    print(f"  {'─'*50}")

    if total_failed == 0:
        _ok("日期异常数据清理完成")
    else:
        _warn(f"清理完成，但有 {total_failed} 只股票失败，请检查日志")


# ──────────────────────────────────────────────────────────────────
# 内部辅助：--no-open-date 模式
# ──────────────────────────────────────────────────────────────────

def _clear_no_open_date(args, service):
    """整个文件删除上市日期缺失标的的缓存"""
    import pandas as pd
    from pathlib import Path as _Path

    period = getattr(args, 'period', None)
    sector = getattr(args, 'sector', None)
    symbols_arg = getattr(args, 'symbols', None)
    skip_confirm = getattr(args, 'yes', False)

    _header("🗑  删除上市日期缺失标的的缓存文件")

    # 解析股票列表
    if symbols_arg:
        symbols = [s.strip() for s in symbols_arg.split(',') if s.strip()]
        _info(f"来源：指定代码（{len(symbols)} 只）")
    elif sector:
        symbols, _ = _resolve_symbols(args, service)
        _info(f"来源：板块 {sector}（{len(symbols)} 只）")
    else:
        _info("来源：全量缓存（未指定 --sector / --symbols）")
        try:
            from data_manager.storage import get_default_storage
            _storage = get_default_storage()
            if period:
                symbols = _storage.list_symbols(period)
            else:
                _all_syms = set()
                for _p in _storage.list_periods():
                    _all_syms.update(_storage.list_symbols(_p))
                symbols = sorted(_all_syms)
        except Exception as _e:
            _err(f"获取全量缓存列表失败：{_e}")
            sys.exit(1)

    if not symbols:
        _warn("未找到任何股票，退出")
        return

    if period:
        _info(f"周期：{period}")
    else:
        _info("周期：全部")

    # ── 获取 SubTypeConfig（validate 所需）────────────────────
    try:
        from data_manager.asset_types import get_asset_type
        _at_cfg = get_asset_type('stock')
        _sub_cfg = _at_cfg.get_sub_type('kline') if _at_cfg else None
        if _sub_cfg is None:
            _err("无法获取 stock/kline 子类配置")
            sys.exit(1)
    except Exception as _e:
        _err(f"获取子类配置失败：{_e}")
        sys.exit(1)

    # ── 预扫描：找出上市日期缺失的标的 ──────────────────────
    _info("正在预扫描上市日期缺失标的...")

    def _on_scan_progress(done, total_cnt):
        if total_cnt > 0 and (done % max(1, total_cnt // 10) == 0 or done == total_cnt):
            print(f"\r  扫描进度：{done}/{total_cnt}", end="", flush=True)

    try:
        from data_manager.data_integrity import batch_validate

        _cache_root = _Path.home() / '.quant' / 'cache'
        _instrument_path = _cache_root / 'stock' / 'instrument' / 'instrument_detail.parquet'
        if not _instrument_path.exists():
            _err("合约信息缺失，请先执行 sync --asset stock --sub instrument")
            sys.exit(1)

        try:
            _trading_dates = service._fetch_trading_dates_sorted()
        except Exception as e:
            _err(str(e))
            sys.exit(1)

        _instrument_df = pd.read_parquet(_instrument_path, engine='pyarrow')

        _validate_results = batch_validate(
            symbol_list=symbols,
            period=period or '1d',
            sub_type_config=_sub_cfg,
            trading_dates_sorted=_trading_dates,
            instrument_df=_instrument_df,
            on_progress=_on_scan_progress,
        )
        print()  # 换行

        _no_open_date_list = [
            r for r in _validate_results
            if r.get('no_open_date', False) and r.get('has_cache', False)
        ]
    except Exception as _e:
        print()
        _err(f"预扫描失败：{_e}")
        sys.exit(1)

    if not _no_open_date_list:
        _ok(f"扫描完成，未发现上市日期缺失的标的（共扫描 {len(symbols)} 只）")
        return

    # ── 展示预览 ──────────────────────────────────────────────
    print(f"\n  发现 {len(_no_open_date_list)} 只上市日期缺失的标的：")
    MAX_PREVIEW = 15
    for _r in _no_open_date_list[:MAX_PREVIEW]:
        try:
            from data_manager.storage import get_default_storage as _get_st2
            _fp = _get_st2()._get_file_path(_r['symbol'], period or '1d')
            _size_kb = round(_fp.stat().st_size / 1024, 1) if _fp.exists() else 0
            print(
                f"    {_r['symbol']:<16}  "
                f"缓存：{_r.get('cache_start', '?')} ~ {_r.get('cache_end', '?')}  "
                f"大小：{_size_kb} KB"
            )
        except Exception:
            print(f"    {_r['symbol']:<16}  缓存：{_r.get('cache_start', '?')} ~ {_r.get('cache_end', '?')}")
    if len(_no_open_date_list) > MAX_PREVIEW:
        _warn(f"  （仅显示前 {MAX_PREVIEW} 只，共 {len(_no_open_date_list)} 只）")

    # ── 二次确认 ──────────────────────────────────────────────
    if not skip_confirm:
        confirm = input(
            f"\n  {_YELLOW}将删除以上 {len(_no_open_date_list)} 只标的的整个缓存文件，"
            f"此操作不可撤销！{_RESET}\n  确认请输入 yes："
        )
        if confirm.strip().lower() != 'yes':
            _info("已取消")
            return

    # ── 执行删除 ──────────────────────────────────────────────
    print()
    _info("开始删除...")

    from data_manager.cache_manager import batch_delete_no_open_date as _batch_del

    def _on_del_progress(done, total_cnt):
        if total_cnt > 0 and (done % max(1, total_cnt // 10) == 0 or done == total_cnt):
            print(f"\r  删除进度：{done}/{total_cnt}", end="", flush=True)

    _del_result = _batch_del(
        symbol_list=[r['symbol'] for r in _no_open_date_list],
        period=period,
        on_progress=_on_del_progress,
    )
    print()  # 换行

    # ── 输出汇总 ──────────────────────────────────────────────
    print(f"\n  {'─'*50}")
    print(f"  清理汇总：")
    print(f"    扫描总数：{len(symbols)} 只")
    print(f"    发现上市日期缺失：{len(_no_open_date_list)} 只")
    print(f"    成功删除：{_del_result.get('deleted', 0)} 只")
    if _del_result.get('failed', 0) > 0:
        print(f"    失败：{_del_result['failed']} 只")
        for _err_item in _del_result.get('errors', []):
            _warn(f"  删除失败：{_err_item['symbol']}  {_err_item['error']}")
    print(f"    释放空间：{_del_result.get('freed_mb', 0.0):.4f} MB")
    print(f"  {'─'*50}")

    if _del_result.get('failed', 0) == 0:
        _ok("上市日期缺失标的缓存删除完成，建议重新同步数据")
    else:
        _warn(f"删除完成，但有 {_del_result['failed']} 只股票失败，请检查日志")
