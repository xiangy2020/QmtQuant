#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard_export.py — 数据看板导出脚本

运行此脚本，将本地缓存统计信息导出为 dashboard_data.json，
然后用浏览器打开 dashboard.html 即可查看数据看板。

用法：
    python dashboard_export.py
    python dashboard_export.py --output /path/to/dashboard_data.json
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 将项目根目录加入 sys.path，确保可以导入 data_manager 等模块
sys.path.insert(0, str(Path(__file__).parent.parent))


def discover_kline_periods(cache_root: Path) -> list:
    """
    任务1：自动发现本地 stock/kline 缓存目录下所有已有数据的周期。

    扫描 ~/.qmtquant/cache/stock/kline/ 目录，返回所有子目录名（即周期列表）。

    Returns:
        已排序的周期列表，如 ['1d', '1m', '5m']；若目录不存在则返回空列表。
    """
    kline_dir = cache_root / "stock" / "kline"
    if not kline_dir.exists():
        return []
    periods = sorted(d.name for d in kline_dir.iterdir() if d.is_dir())
    return periods


def check_aux_data_available(cache_root: Path) -> tuple:
    """
    任务2：检查辅助数据（交易日历 + 合约信息）是否可用。

    Returns:
        (available: bool, reason: str)
        available=True 表示两个文件均存在，可以执行完整性检查。
        available=False 时 reason 说明缺失的文件。
    """
    calendar_path = cache_root / "stock" / "calendar" / "trading_calendar.parquet"
    instrument_path = cache_root / "stock" / "instrument" / "instrument_detail.parquet"

    missing = []
    if not calendar_path.exists():
        missing.append("trading_calendar.parquet")
    if not instrument_path.exists():
        missing.append("instrument_detail.parquet")

    if missing:
        return False, f"缺少辅助数据文件：{', '.join(missing)}"
    return True, ""


def collect_validate_results(cache_root: Path, periods: list) -> dict:
    """
    任务3：对每个周期执行完整性检查，返回 validate_by_period 字典。

    对每个周期：
      1. 获取该周期下所有已缓存的股票列表
      2. 调用 DataService.validate_kline() 执行批量检查
      3. 将 summary 和精简后的 results 写入字典

    Returns:
        {
            "1d": { "summary": {...}, "results": [...] },
            "1m": { "summary": {...}, "results": [...] },
            ...
        }
    """
    try:
        from data_manager.data_service import DataService
        from data_manager.asset_types import STOCK
        from data_manager.storage import Storage
    except ImportError as e:
        print(f"  ⚠ 无法导入 DataService，跳过完整性检查：{e}", file=sys.stderr)
        return {"_skipped": True, "reason": f"导入失败：{e}"}

    # 获取 stock/kline 的 SubTypeConfig
    kline_config = STOCK.get_sub_type("kline")
    if kline_config is None:
        return {"_skipped": True, "reason": "找不到 stock/kline 子类配置"}

    service = DataService()
    storage = Storage(cache_root=str(cache_root / "stock"))

    validate_by_period = {}

    for period in periods:
        print(f"  正在检查周期 [{period}]...")
        try:
            # 获取该周期下所有股票
            stock_list = storage.list_symbols(period)
            if not stock_list:
                print(f"    ⚠ 周期 [{period}] 无缓存数据，跳过")
                continue

            print(f"    共 {len(stock_list)} 只股票，开始检查...")

            # 进度回调（每 100 只打印一次）
            _progress_counter = [0]

            class _ProgressCallbacks:
                def on_progress(self, done, total):
                    _progress_counter[0] = done
                    if done % 100 == 0 and done > 0:
                        print(f"    进度：{done}/{total}")

                def on_log(self, message):
                    pass

                def on_error(self, error):
                    print(f"    ⚠ {error}", file=sys.stderr)

                def on_done(self, result):
                    pass

            result = service.validate_kline(
                params={
                    "stock_list": stock_list,
                    "period": period,
                    "sub_type_config": kline_config,
                },
                callbacks=_ProgressCallbacks(),
            )

            # 构建 summary
            raw_results = result.get("results", [])
            has_gap_count = sum(
                1 for r in raw_results if r.get("gap_segments")
            )
            no_open_date_count = sum(
                1 for r in raw_results if r.get("no_open_date")
            )
            summary = {
                "period":        period,
                "total":         result.get("total", 0),
                "healthy":       result.get("healthy", 0),
                "no_cache":      result.get("no_cache", 0),
                "field_error":   result.get("field_error", 0),
                "type_error":    result.get("type_error", 0),
                "head_missing":  result.get("head_missing", 0),
                "tail_missing":  result.get("tail_missing", 0),
                "no_open_date":  no_open_date_count,
                "has_gap":       has_gap_count,
                "checked_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 构建精简 results（只保留 dashboard 需要的字段）
            slim_results = []
            for r in raw_results:
                slim_results.append({
                    "symbol":       r.get("symbol"),
                    "has_cache":    r.get("has_cache", False),
                    "field_ok":     r.get("field_ok", True),
                    "type_ok":      r.get("type_ok", True),
                    "head_missing": r.get("head_missing", 0),
                    "tail_missing": r.get("tail_missing", 0),
                    "gap_count":    len(r.get("gap_segments") or []),
                    "no_open_date": r.get("no_open_date", False),
                    "cache_start":  r.get("cache_start"),
                    "cache_end":    r.get("cache_end"),
                })

            validate_by_period[period] = {
                "summary": summary,
                "results": slim_results,
            }

            # 打印该周期汇总
            print(
                f"    ✓ [{period}] 完成：总计 {summary['total']} 只，"
                f"健康 {summary['healthy']}，"
                f"前缺失 {summary['head_missing']}，"
                f"后缺失 {summary['tail_missing']}，"
                f"中间缺口 {summary['has_gap']}，"
                f"无缓存 {summary['no_cache']}"
            )

        except Exception as e:
            print(f"    ⚠ 周期 [{period}] 检查失败，已跳过：{e}", file=sys.stderr)
            continue

    return validate_by_period


def collect_backtest_results(base_dir: Path) -> list:
    """
    扫描 backtest_results/ 目录，收集所有回测记录。

    每个子目录对应一次回测，必须包含 summary.csv；
    config.csv 和 trades.csv 为可选文件。

    返回按目录修改时间降序排列的回测记录列表。
    """
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    results = []

    for sub_dir in base_dir.iterdir():
        if not sub_dir.is_dir():
            continue

        summary_path = sub_dir / "summary.csv"
        if not summary_path.exists():
            print(f"  ⚠ 跳过 {sub_dir.name}：缺少 summary.csv", file=sys.stderr)
            continue

        record = {
            "dir_name": sub_dir.name,
            "mtime": datetime.fromtimestamp(sub_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "_mtime_ts": sub_dir.stat().st_mtime,  # 用于排序，最终不输出
            "strategy_name": None,
            "start_time": None,
            "end_time": None,
            "init_capital": None,
            "final_capital": None,
            "total_return": None,
            "annual_return": None,
            "max_drawdown": None,
            "trade_days": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "volatility": None,
            "alpha": None,
            "beta": None,
            "risk_free_rate": None,
            "win_rate": None,
            "profit_loss_ratio": None,
            "trade_count": None,
            "benchmark": None,
        }

        # 读取 summary.csv
        try:
            with open(summary_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if row:
                    def _float(v):
                        try:
                            return float(v) if v not in (None, "", "None") else None
                        except (ValueError, TypeError):
                            return None

                    def _int(v):
                        try:
                            return int(float(v)) if v not in (None, "", "None") else None
                        except (ValueError, TypeError):
                            return None

                    record["init_capital"]      = _float(row.get("init_capital"))
                    record["final_capital"]     = _float(row.get("final_capital"))
                    record["total_return"]      = _float(row.get("total_return"))
                    record["annual_return"]     = _float(row.get("annual_return"))
                    record["max_drawdown"]      = _float(row.get("max_drawdown"))
                    record["trade_days"]        = _int(row.get("trade_days"))
                    record["sharpe_ratio"]      = _float(row.get("sharpe_ratio"))
                    record["sortino_ratio"]     = _float(row.get("sortino_ratio"))
                    record["volatility"]        = _float(row.get("volatility"))
                    record["alpha"]             = _float(row.get("alpha"))
                    record["beta"]              = _float(row.get("beta"))
                    record["risk_free_rate"]    = _float(row.get("risk_free_rate"))
                    record["win_rate"]          = _float(row.get("win_rate"))
                    record["profit_loss_ratio"] = _float(row.get("profit_loss_ratio"))
        except Exception as e:
            print(f"  ⚠ 读取 {sub_dir.name}/summary.csv 失败：{e}", file=sys.stderr)
            continue

        # 读取 config.csv（可选）
        config_path = sub_dir / "config.csv"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    row = next(reader, None)
                    if row:
                        # 从 strategy_file 路径中解析文件名（不含扩展名）
                        strategy_file = row.get("strategy_file", "")
                        if strategy_file:
                            record["strategy_name"] = Path(strategy_file).stem
                        record["start_time"]  = row.get("start_time") or None
                        record["end_time"]    = row.get("end_time") or None
                        record["init_capital"] = record["init_capital"] or (
                            float(row["init_capital"])
                            if row.get("init_capital") not in (None, "", "None")
                            else None
                        )
                        record["benchmark"]   = row.get("benchmark") or None
            except Exception as e:
                print(f"  ⚠ 读取 {sub_dir.name}/config.csv 失败：{e}", file=sys.stderr)

        # 读取 daily_stats.csv（可选）
        daily_stats_path = sub_dir / "daily_stats.csv"
        daily_stats_list = []
        if daily_stats_path.exists():
            try:
                init_cap = record.get("init_capital") or 1.0
                with open(daily_stats_path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        def _fv(v):
                            try:
                                return float(v) if v not in (None, "", "None") else None
                            except (ValueError, TypeError):
                                return None

                        total_asset = _fv(row.get("total_asset"))
                        nav = round(total_asset / init_cap, 6) if total_asset is not None and init_cap else None
                        daily_stats_list.append({
                            "date":            row.get("date"),
                            "total_asset":     total_asset,
                            "cash":            _fv(row.get("cash")),
                            "market_value":    _fv(row.get("market_value")),
                            "daily_return":    _fv(row.get("daily_return")),
                            "benchmark_close": _fv(row.get("benchmark_close")),
                            "nav":             nav,
                        })
            except Exception as e:
                print(f"  ⚠ 读取 {sub_dir.name}/daily_stats.csv 失败：{e}", file=sys.stderr)
        record["daily_stats"] = daily_stats_list

        # 读取 benchmark.csv（可选）
        benchmark_path = sub_dir / "benchmark.csv"
        benchmark_list = []
        if benchmark_path.exists():
            try:
                with open(benchmark_path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                first_close = None
                for row in rows:
                    try:
                        close_val = float(row.get("close", "") or 0)
                    except (ValueError, TypeError):
                        close_val = None
                    if first_close is None and close_val:
                        first_close = close_val
                    benchmark_nav = round(close_val / first_close, 6) if (close_val and first_close) else None
                    benchmark_list.append({
                        "date":          row.get("date"),
                        "close":         close_val,
                        "benchmark_nav": benchmark_nav,
                    })
            except Exception as e:
                print(f"  ⚠ 读取 {sub_dir.name}/benchmark.csv 失败：{e}", file=sys.stderr)
        record["benchmark_data"] = benchmark_list

        # 读取 trades.csv（可选）
        trades_path = sub_dir / "trades.csv"
        trades_list = []
        if trades_path.exists():
            try:
                with open(trades_path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        trades_list.append(dict(row))
                record["trade_count"] = len(trades_list)
            except Exception as e:
                print(f"  ⚠ 读取 {sub_dir.name}/trades.csv 失败：{e}", file=sys.stderr)
        record["trades"] = trades_list

        results.append(record)

    # 按修改时间降序排列
    results.sort(key=lambda r: r["_mtime_ts"], reverse=True)

    # 移除排序辅助字段
    for r in results:
        r.pop("_mtime_ts", None)

    return results


def main():
    parser = argparse.ArgumentParser(description="导出数据看板 JSON 数据")
    parser.add_argument(
        "--output", "-o",
        default=str(Path(__file__).parent / "dashboard_data.json"),
        help="输出 JSON 文件路径（默认：dashboard/dashboard_data.json）",
    )
    args = parser.parse_args()

    print("正在收集缓存统计信息，请稍候（首次运行可能需要几分钟）...")

    try:
        from data_manager.cache_manager import get_statistics
    except ImportError as e:
        print(f"错误：无法导入 data_manager，请确认在项目根目录运行：{e}", file=sys.stderr)
        sys.exit(1)

    try:
        stats = get_statistics()
    except Exception as e:
        print(f"错误：获取统计信息失败：{e}", file=sys.stderr)
        sys.exit(1)

    # 收集回测结果
    backtest_dir = Path(__file__).parent.parent / "backtest_results"
    print("正在扫描回测结果目录...")
    backtest_results = collect_backtest_results(backtest_dir)
    stats["backtest_results"] = backtest_results
    print(f"  ✓ 共找到 {len(backtest_results)} 条回测记录")

    # 任务4：采集完整性检查数据（多周期）
    cache_root = Path.home() / ".qmtquant" / "cache"
    print("正在检查辅助数据可用性...")
    aux_ok, aux_reason = check_aux_data_available(cache_root)
    if not aux_ok:
        print(f"  ⚠ {aux_reason}，跳过完整性检查", file=sys.stderr)
        print(f"    提示：请先执行 dm sync --asset stock --sub calendar 和 dm sync --asset stock --sub instrument")
        stats["validate_by_period"] = {"_skipped": True, "reason": aux_reason}
    else:
        periods = discover_kline_periods(cache_root)
        if not periods:
            print("  ⚠ 未发现任何 stock/kline 缓存周期，跳过完整性检查")
            stats["validate_by_period"] = {"_skipped": True, "reason": "未发现任何 stock/kline 缓存周期"}
        else:
            print(f"  ✓ 发现周期：{periods}，开始完整性检查...")
            validate_by_period = collect_validate_results(cache_root, periods)
            stats["validate_by_period"] = validate_by_period
            print(f"  ✓ 完整性检查完成，共检查 {len(validate_by_period)} 个周期")

    # 附加导出时间戳
    stats["exported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output_path = Path(args.output)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
        print(f"✓ 数据已导出到：{output_path}")
        print(f"  请用浏览器打开 dashboard/dashboard.html 查看看板")
    except Exception as e:
        print(f"错误：写入文件失败：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
