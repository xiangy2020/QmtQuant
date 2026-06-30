# -*- coding: utf-8 -*-
"""
bt_cli.py — 回测模块 CLI 入口

用法：
    python bt_cli.py <命令> [选项]

命令列表：
    run         运行回测（传入 .qmt 配置文件，支持参数覆盖）
list        列出 strategy/ 目录下的策略文件
    results     查看本地回测结果汇总

示例：
    python bt_cli.py list
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt
  python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --start 20240101 --end 20241231
  python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --capital 500000 --init-data
    python bt_cli.py results
    python bt_cli.py results --detail --limit 10
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 模块级别提前压制底层 RPC 噪音日志 ──────────────────────────────
# 必须在任何 import env / xqshare / xtquant 之前生效，
# 否则连接阶段的 INFO 日志已经输出，_setup_logging 里的压制来不及。
# 覆盖两路噪音：
#   1. xtquant_client  — xqshare/client.py 的 RPC 调用日志（[CALL]/[OK]）
#   2. api / xqshare.server — xqshare/server.py 的服务端 API 日志
#   3. xqshare / xtquant / xtdata — 其他底层模块
for _noisy in ("xtquant_client", "api", "xqshare", "xqshare.server", "xtquant", "xtdata"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# xqshare client 的 _logger 是懒加载的，可能在我们压制前已被初始化并挂上 StreamHandler。
# 直接移除 xtquant_client logger 上所有 StreamHandler，并重置懒加载状态。
try:
    import xqshare.client as _xqs_client
    _xqs_client.set_quiet_mode(True)
    # 强制重置懒加载 logger，让下次 get_logger() 用 quiet=True 重新初始化
    _xqs_client._logger = None
    # 提前触发 get_logger() 初始化（quiet=True），防止后续 RPC 调用时懒加载重新挂 StreamHandler
    _xqs_client.get_logger()
    # 再次确认：清理 xtquant_client logger 上所有 StreamHandler
    _xtq_logger = logging.getLogger("xtquant_client")
    for _h in list(_xtq_logger.handlers):
        if isinstance(_h, logging.StreamHandler) and not isinstance(_h, logging.FileHandler):
            _xtq_logger.removeHandler(_h)
    _xtq_logger.propagate = False  # 禁止向 root logger 传播
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────
# 颜色常量与日志工具（与 dm_cli.py 保持一致）
# ──────────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # xqshare/server.py 的 setup_logging 会给 root logger 挂 StreamHandler，
    # 导致所有日志都被输出，子 logger 级别设置失效。
    # 这里清理 root logger 上所有 StreamHandler，只保留 basicConfig 添加的那个。
    root = logging.getLogger()
    # 移除 xqshare 添加的多余 StreamHandler（保留 basicConfig 的第一个）
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.FileHandler)]
    if len(stream_handlers) > 1:
        for h in stream_handlers[1:]:
            root.removeHandler(h)

    # 压制底层 RPC / xqshare 的 INFO 噪音日志，无论是否 verbose 都只保留 WARNING+
    _NOISY_LOGGERS = [
        "xtquant_client", "api", "xqshare", "xqshare.server", "xtquant", "xtdata",
    ]
    for _name in _NOISY_LOGGERS:
        _nl = logging.getLogger(_name)
        _nl.setLevel(logging.WARNING)
        # 移除所有 StreamHandler，防止 xqshare 懒加载时重新挂上控制台输出
        for _h in list(_nl.handlers):
            if isinstance(_h, logging.StreamHandler) and not isinstance(_h, logging.FileHandler):
                _nl.removeHandler(_h)
        _nl.propagate = False  # 禁止向 root logger 传播，彻底切断输出路径


def _ok(msg: str):
    print(f"{_GREEN}✓{_RESET} {msg}")


def _warn(msg: str):
    print(f"{_YELLOW}⚠{_RESET} {msg}", file=sys.stderr)


def _err(msg: str):
    print(f"{_RED}✗{_RESET} {msg}", file=sys.stderr)


def _info(msg: str):
    print(f"  {msg}")


def _header(msg: str):
    print(f"\n{_BOLD}{_CYAN}{msg}{_RESET}")


# ──────────────────────────────────────────────────────────────────
# CLI 框架回调适配器
# ──────────────────────────────────────────────────────────────────

class CliFrameworkCallbacks:
    """
    FrameworkCallbacks 协议的 CLI 实现。

纯 Python 类，零 mock。
    直接将框架回调输出到终端。
    """

    _LEVEL_COLOR = {
        "DEBUG":   "\033[90m",   # 灰色
        "INFO":    "",
        "WARNING": _YELLOW,
        "ERROR":   _RED,
        "TRADE":   _CYAN,
    }

    def __init__(self, verbose: bool = False):
        self._verbose = verbose

    def on_log(self, message: str, level: str = "INFO") -> None:
        """
        将框架日志输出到终端。
        非 verbose 模式下输出 INFO / WARNING / ERROR / TRADE（过滤 DEBUG）；
        verbose 模式下输出全部级别（含 DEBUG）。
        """
        if not self._verbose and level == "DEBUG":
            return
        color = self._LEVEL_COLOR.get(level, "")
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  {color}[{level}]{_RESET} {ts}  {message}")

    def on_progress(self, pct: int) -> None:
        pass  # CLI 模式下默认静默

    def on_period_mismatch(self, message: str) -> bool:
        """
        打印警告后默认返回 True（继续运行，不阻塞）。
        """
        _warn(f"数据周期与触发类型不匹配，默认继续运行：\n{message}")
        return True

    def on_t0_warning(self, message: str) -> None:
        """T+0 混合池警告，以黄色 ⚠ 格式打印到终端。"""
        _warn(f"T+0 模式警告：{message}")

    def on_finished(self) -> None:
        pass  # CLI 模式下默认静默

# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def _project_root() -> Path:
    """返回项目根目录（本文件所在目录）。"""
    return Path(__file__).parent


def _load_config(config_path: str) -> dict:
    """
    加载 .qmt 配置文件（JSON 格式）。
    失败时打印错误并 sys.exit(1)。
    """
    path = Path(config_path)
    if not path.exists():
        _err(f"配置文件不存在：{config_path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        _err(f"配置文件 JSON 解析失败：{e}")
        sys.exit(1)
    except Exception as e:
        _err(f"读取配置文件失败：{e}")
        sys.exit(1)


def _apply_overrides(config: dict, args) -> dict:
    """
    将 CLI 参数覆盖到配置字典中。
    只覆盖用户明确传入的参数，未传入的保持配置文件原值。
    """
    bt = config.setdefault("backtest", {})

    if getattr(args, "start", None):
        bt["start_time"] = args.start
    if getattr(args, "end", None):
        bt["end_time"] = args.end
    if getattr(args, "capital", None) is not None:
        bt["init_capital"] = float(args.capital)
    if getattr(args, "benchmark", None):
        bt["benchmark"] = args.benchmark
    if getattr(args, "trigger", None):
        bt.setdefault("trigger", {})["type"] = args.trigger
    if getattr(args, "strategy", None):
        config["strategy_file"] = args.strategy
    if getattr(args, "risk_free_rate", None) is not None:
        config.setdefault("backtest", {})["risk_free_rate"] = float(args.risk_free_rate)

    # 强制 run_mode = backtest
    config["run_mode"] = "backtest"
    return config


def _write_temp_config(config: dict) -> str:
    """将配置写入 config/temp_bt_cli_config.qmt，返回路径字符串。"""
    config_dir = _project_root() / "config"
    config_dir.mkdir(exist_ok=True)
    tmp_path = config_dir / "temp_bt_cli_config.qmt"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return str(tmp_path)


def _print_result_summary(verbose: bool = False):
    """回测完成后，找到最新结果目录并打印核心指标。"""
    results_dir = _project_root() / "backtest_results"
    if not results_dir.exists():
        return

    subdirs = sorted(
        [d for d in results_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not subdirs:
        return

    latest = subdirs[0]
    summary_file = latest / "summary.csv"
    if not summary_file.exists():
        _warn(f"未找到汇总文件：{summary_file}")
        return

    try:
        import pandas as pd
        df = pd.read_csv(summary_file)
        if df.empty:
            return
        row = df.iloc[0]

        _header("📊 回测结果汇总")
        _info(f"结果目录：{latest.name}")
        print()

        init_cap   = float(row.get("init_capital", 0))
        final_cap  = float(row.get("final_capital", 0))
        total_ret  = float(row.get("total_return", 0))
        annual_ret = float(row.get("annual_return", 0))
        max_dd     = float(row.get("max_drawdown", 0))
        trade_days = int(row.get("trade_days", 0))

        col_k = 14
        col_v = 20
        print(f"  {'初始资金':<{col_k}} {init_cap:>{col_v},.2f} 元")
        print(f"  {'最终资产':<{col_k}} {final_cap:>{col_v},.2f} 元")

        ret_color = _GREEN if total_ret >= 0 else _RED
        print(f"  {'总收益率':<{col_k}} {ret_color}{total_ret:>{col_v}.2f}%{_RESET}")
        print(f"  {'年化收益率':<{col_k}} {ret_color}{annual_ret:>{col_v}.2f}%{_RESET}")
        print(f"  {'最大回撤':<{col_k}} {_RED}{max_dd:>{col_v}.2f}%{_RESET}")
        print(f"  {'回测交易日':<{col_k}} {trade_days:>{col_v}} 天")

        # 交易笔数
        trades_file = latest / "trades.csv"
        if trades_file.exists():
            try:
                trades_df = pd.read_csv(trades_file)
                print(f"  {'交易笔数':<{col_k}} {len(trades_df):>{col_v}} 笔")
            except Exception:
                pass

        print()
        _info(f"完整结果：{latest}")

    except Exception as e:
        _warn(f"读取汇总结果失败：{e}")


# ──────────────────────────────────────────────────────────────────
# 任务 3 + 4：run 子命令
# ──────────────────────────────────────────────────────────────────

def cmd_run(args):
    """运行回测。"""
    # ── 加载配置 ──────────────────────────────────────────────────
    config = _load_config(args.config)

    # ── 应用 CLI 参数覆盖 ─────────────────────────────────────────
    config = _apply_overrides(config, args)

    # ── 校验 strategy_file ────────────────────────────────────────
    strategy_file = config.get("strategy_file", "").strip()
    if not strategy_file:
        _err("配置文件中未指定 strategy_file，请检查 .qmt 文件或使用 --strategy 参数")
        sys.exit(1)

    def _is_windows_abs_path(p: str) -> bool:
        """判断是否为 Windows 风格绝对路径（如 C:/... 或 C:\\...）。"""
        return len(p) >= 3 and p[1] == ":" and p[2] in ("/", "\\")

    if os.path.isabs(strategy_file):
        # Unix 绝对路径，直接使用
        strategy_file_abs = strategy_file
    elif _is_windows_abs_path(strategy_file):
        # Windows 绝对路径（在 Mac/Linux 上无法直接使用），
        # 取文件名后在项目根目录下查找同名文件
        win_filename = Path(strategy_file.replace("\\", "/")).name
        candidate = _project_root() / "strategy" / win_filename
        if candidate.exists():
            strategy_file_abs = str(candidate)
            _warn(
                f"配置文件中的策略路径为 Windows 格式，已自动映射到本地：\n"
                f"  原路径：{strategy_file}\n"
                f"  映射到：{strategy_file_abs}"
            )
        else:
            # 在整个项目根目录下递归查找
            matches = list(_project_root().rglob(win_filename))
            if matches:
                strategy_file_abs = str(matches[0])
                _warn(
                    f"配置文件中的策略路径为 Windows 格式，已自动映射到本地：\n"
                    f"  原路径：{strategy_file}\n"
                    f"  映射到：{strategy_file_abs}"
                )
            else:
                _err(
                    f"配置文件中的策略路径为 Windows 格式，且在本地找不到同名文件：{win_filename}\n"
                    f"  原路径：{strategy_file}\n"
f"  请将策略文件放到 strategy/ 目录下，或使用 --strategy 参数指定本地路径"
                )
                sys.exit(1)
    else:
        # 相对路径以项目根目录为基准
        strategy_file_abs = str(_project_root() / strategy_file)

    if not Path(strategy_file_abs).exists():
        _err(f"策略文件不存在：{strategy_file_abs}")
        sys.exit(1)

    # ── 打印回测参数摘要 ──────────────────────────────────────────
    bt = config.get("backtest", {})
    start_time   = bt.get("start_time", "—")
    end_time     = bt.get("end_time", "—")
    init_capital = bt.get("init_capital", 1_000_000)
    benchmark    = bt.get("benchmark", "sh.000300")
    trigger_type = bt.get("trigger", {}).get("type", "—")
    period       = config.get("data", {}).get("kline_period", trigger_type)
    init_data    = getattr(args, "init_data", False)
    verbose      = getattr(args, "verbose", False)

    _header("🚀 开始回测")
    _info(f"配置文件：{args.config}")
    _info(f"策略文件：{strategy_file_abs}")
    _info(f"回测区间：{start_time} ~ {end_time}")
    _info(f"初始资金：{init_capital:,.0f} 元")
    _info(f"基准指数：{benchmark}")
    _info(f"数据周期：{period}  触发类型：{trigger_type}")
    _info(f"初始化数据：{'是（将触发历史数据下载）' if init_data else '否（使用本地缓存）'}")
    print()

    # ── 写临时配置文件 ──────────────────────────────────────────
    tmp_config_path = _write_temp_config(config)

    # ── 导入框架 ──────────────────────────────────────────────────
    try:
        from framework import QuantFramework
    except ImportError as e:
        _err(f"无法导入 QuantFramework：{e}")
        _err("请确认 framework.py 在当前目录或 PYTHONPATH 中")
        sys.exit(1)

    # ── 实例化并运行（使用 CliFrameworkCallbacks，无需任何 mock）──
    cli_callbacks = CliFrameworkCallbacks(verbose=verbose)
    framework = QuantFramework(
        config_path=tmp_config_path,
        strategy_file=strategy_file_abs,
        callbacks=cli_callbacks,
    )

    risk_free_rate = getattr(args, "risk_free_rate", None)

    start_ts = time.time()
    try:
        framework.run(init_data_enabled=init_data, risk_free_rate=risk_free_rate)
    except KeyboardInterrupt:
        print()
        _warn("回测已被用户中断（Ctrl+C）")
        sys.exit(130)
    except Exception as e:
        print()
        _err(f"回测执行失败：{e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_ts
    print()
    _ok(f"回测完成，耗时 {elapsed:.1f}s")

    # ── 打印结果汇总 ──────────────────────────────────────────────
    _print_result_summary(verbose=verbose)


# ──────────────────────────────────────────────────────────────────
# 任务 5：list 子命令
# ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    """列出 strategy/ 目录下的策略文件。"""
    strategy_dir = _project_root() / "strategy"

    _header("📋 本地策略列表")

    if not strategy_dir.exists():
        _warn(f"strategy/ 目录不存在：{strategy_dir}")
        _info("请先创建策略目录并放入 .qmt 配置文件")
        return

    qmt_files = sorted(strategy_dir.rglob("*.qmt"))
    if not qmt_files:
        _warn("未找到任何 .qmt 策略配置文件")
        _info(f"策略目录：{strategy_dir}")
        return

    print()
    col_name    = 40
    col_period  = 8
    col_range   = 26
    col_capital = 14

    hdr = (f"  {'策略配置文件':<{col_name}} {'周期':<{col_period}}"
           f" {'回测区间':<{col_range}} {'初始资金':>{col_capital}}")
    sep = (f"  {'─'*col_name} {'─'*col_period}"
           f" {'─'*col_range} {'─'*col_capital}")
    print(hdr)
    print(sep)

    for qmt_file in qmt_files:
        rel_path = str(qmt_file.relative_to(_project_root()))
        try:
            cfg = _load_config(str(qmt_file))
            bt      = cfg.get("backtest", {})
            data    = cfg.get("data", {})
            period  = data.get("kline_period", bt.get("trigger", {}).get("type", "—"))
            start   = bt.get("start_time", "—")
            end     = bt.get("end_time", "—")
            capital = bt.get("init_capital", 0)
            range_str   = f"{start} ~ {end}"
            capital_str = f"{capital:,.0f}" if capital else "—"
        except SystemExit:
            # _load_config 内部会 sys.exit，这里捕获后继续
            period      = "?"
            range_str   = "（解析失败）"
            capital_str = "—"
        except Exception:
            period      = "?"
            range_str   = "（解析失败）"
            capital_str = "—"

        print(f"  {rel_path:<{col_name}} {period:<{col_period}}"
              f" {range_str:<{col_range}} {capital_str:>{col_capital}}")

    print()
    _info(f"共 {len(qmt_files)} 个策略配置文件")
    print()
    _info("运行策略：python bt_cli.py run <策略配置文件路径>")


# ──────────────────────────────────────────────────────────────────
# 任务 6：results 子命令
# ──────────────────────────────────────────────────────────────────

def cmd_results(args):
    """查看本地回测结果汇总。"""
    results_dir = _project_root() / "backtest_results"

    _header("📊 本地回测结果")

    if not results_dir.exists() or not any(results_dir.iterdir()):
        _warn("暂无回测结果，请先运行 run 命令")
        _info("示例：python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt")
        return

    subdirs = sorted(
        [d for d in results_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not subdirs:
        _warn("暂无回测结果，请先运行 run 命令")
        return

    try:
        import pandas as pd
    except ImportError:
        _err("需要安装 pandas：pip install pandas")
        sys.exit(1)

    show_detail = getattr(args, "detail", False)
    limit       = getattr(args, "limit", 20)

    # ── 收集每条结果的指标 ────────────────────────────────────────
    rows = []
    for d in subdirs:
        mtime = datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        summary_file = d / "summary.csv"
        if not summary_file.exists():
            rows.append({"dir": d.name, "mtime": mtime,
                         "total_return": None, "annual_return": None,
                         "max_drawdown": None, "trade_days": None, "trades": None,
                         "sharpe_ratio": None})
            continue
        try:
            df  = pd.read_csv(summary_file)
            row = df.iloc[0] if not df.empty else {}
            trade_cnt = None
            trades_file = d / "trades.csv"
            if trades_file.exists():
                try:
                    trade_cnt = len(pd.read_csv(trades_file))
                except Exception:
                    pass
            rows.append({
                "dir":          d.name,
                "mtime":        mtime,
                "total_return":  float(row.get("total_return",  0) or 0),
                "annual_return": float(row.get("annual_return", 0) or 0),
                "max_drawdown":  float(row.get("max_drawdown",  0) or 0),
                "trade_days":    int(row.get("trade_days", 0) or 0),
                "trades":        trade_cnt,
                "sharpe_ratio":  float(row["sharpe_ratio"]) if str(row.get("sharpe_ratio", "")).strip() not in ("", "nan", "None") else None,
            })
        except Exception:
            rows.append({"dir": d.name, "mtime": mtime,
                         "total_return": None, "annual_return": None,
                         "max_drawdown": None, "trade_days": None, "trades": None,
                         "sharpe_ratio": None})

    # ── 截断 ──────────────────────────────────────────────────────
    total         = len(rows)
    rows_to_show  = rows[:limit] if limit > 0 else rows
    truncated     = total > len(rows_to_show)

    # ── 表头 ──────────────────────────────────────────────────────
    print()
    col_dir  = 52
    col_time = 17
    col_ret  = 10
    col_ann  = 10
    col_dd   = 10
    col_days =  8
    col_trd  =  8
    col_sharpe = 8

    hdr = (f"  {'结果目录':<{col_dir}} {'时间':<{col_time}}"
           f" {'总收益%':>{col_ret}} {'年化%':>{col_ann}}"
           f" {'最大回撤%':>{col_dd}} {'交易日':>{col_days}} {'笔数':>{col_trd}}"
           f" {'夏普':>{col_sharpe}}")
    sep = (f"  {'─'*col_dir} {'─'*col_time}"
           f" {'─'*col_ret} {'─'*col_ann}"
           f" {'─'*col_dd} {'─'*col_days} {'─'*col_trd}"
           f" {'─'*col_sharpe}")
    print(hdr)
    print(sep)

    for r in rows_to_show:
        def _fmt_ret(v, width):
            if v is None:
                return f"{'—':>{width}}"
            color = _GREEN if v >= 0 else _RED
            return f"{color}{v:>{width}.2f}{_RESET}"

        def _fmt_dd(v, width):
            if v is None:
                return f"{'—':>{width}}"
            return f"{_RED}{v:>{width}.2f}{_RESET}"

        def _fmt_sharpe(v, width):
            if v is None:
                return f"{'—':>{width}}"
            if v > 0:
                return f"{_GREEN}{v:>{width}.2f}{_RESET}"
            elif v < 0:
                return f"{_RED}{v:>{width}.2f}{_RESET}"
            else:
                return f"{v:>{width}.2f}"

        total_ret_str  = _fmt_ret(r["total_return"],  col_ret)
        annual_ret_str = _fmt_ret(r["annual_return"], col_ann)
        dd_str         = _fmt_dd(r["max_drawdown"],   col_dd)
        sharpe_str     = _fmt_sharpe(r.get("sharpe_ratio"), col_sharpe)
        days_str = f"{r['trade_days']:>{col_days}}" if r["trade_days"] is not None else f"{'—':>{col_days}}"
        trd_str  = f"{r['trades']:>{col_trd}}"      if r["trades"]     is not None else f"{'—':>{col_trd}}"

        print(f"  {r['dir']:<{col_dir}} {r['mtime']:<{col_time}}"
              f" {total_ret_str} {annual_ret_str}"
              f" {dd_str} {days_str} {trd_str} {sharpe_str}")

        # ── --detail：展示前 5 条交易记录 ─────────────────────────
        if show_detail:
            trades_file = results_dir / r["dir"] / "trades.csv"
            if trades_file.exists():
                try:
                    tdf = pd.read_csv(trades_file)
                    if not tdf.empty:
                        print(f"    {'─'*76}")
                        print(f"    交易记录（前5条）：")
                        for _, trow in tdf.head(5).iterrows():
                            action = trow.get("action", trow.get("direction", "?"))
                            code   = trow.get("code", "?")
                            price  = float(trow.get("price", 0))
                            volume = int(trow.get("volume", 0))
                            dt     = trow.get("datetime", trow.get("time", "?"))
                            print(f"      {dt}  {str(action):<4} {str(code):<12}"
                                  f"  价格:{price:.2f}  数量:{volume}")
                        print(f"    {'─'*76}")
                except Exception:
                    pass

    if truncated:
        print(f"\n  {_YELLOW}仅显示最近 {len(rows_to_show)} 条，共 {total} 条。"
              f"使用 --limit 0 查看全部{_RESET}")
    else:
        print(f"\n  共 {total} 条回测记录")

    print()
    _info(f"结果目录：{results_dir}")


# ──────────────────────────────────────────────────────────────────
# plot 子命令
# ──────────────────────────────────────────────────────────────────

def cmd_plot(args):
    """绘制回测结果图表（资产曲线、回撤、收益分布、月度热力图）。"""
    try:
        import matplotlib
        if getattr(args, "save", None):
            matplotlib.use("Agg")
        else:
            # 按平台选择交互式后端，避免依赖 tkinter
            import platform
            _sys = platform.system()
            if _sys == "Darwin":
                matplotlib.use("MacOSX")
            elif _sys == "Windows":
                matplotlib.use("TkAgg")
            else:
                # Linux：优先 Qt5Agg，不可用则降级 Agg（仅保存）
                try:
                    matplotlib.use("Qt5Agg")
                except Exception:
                    matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.gridspec as gridspec
        from matplotlib import ticker as mticker
        import pandas as pd
        import numpy as np
    except ImportError as e:
        _err(f"缺少依赖：{e}")
        _err("请安装：pip install matplotlib pandas numpy")
        sys.exit(1)

    # ── 定位结果目录 ──────────────────────────────────────────────
    results_dir = _project_root() / "backtest_results"
    result_path: Path

    if getattr(args, "result_dir", None):
        p = Path(args.result_dir)
        if not p.is_absolute():
            p = _project_root() / p
        if not p.exists():
            # 尝试在 backtest_results/ 下查找
            p2 = results_dir / args.result_dir
            if p2.exists():
                p = p2
            else:
                _err(f"结果目录不存在：{args.result_dir}")
                sys.exit(1)
        result_path = p
    else:
        # 默认取最新结果
        if not results_dir.exists():
            _err("backtest_results/ 目录不存在，请先运行回测")
            sys.exit(1)
        subdirs = sorted(
            [d for d in results_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if not subdirs:
            _err("暂无回测结果，请先运行 run 命令")
            sys.exit(1)
        result_path = subdirs[0]
        _info(f"未指定结果目录，使用最新结果：{result_path.name}")

    # ── 读取数据 ──────────────────────────────────────────────────
    daily_file = result_path / "daily_stats.csv"
    summary_file = result_path / "summary.csv"
    trades_file = result_path / "trades.csv"
    benchmark_file = result_path / "benchmark.csv"

    if not daily_file.exists():
        _err(f"找不到 daily_stats.csv：{daily_file}")
        sys.exit(1)

    try:
        daily_df = pd.read_csv(daily_file, parse_dates=["date"])
        daily_df = daily_df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        _err(f"读取 daily_stats.csv 失败：{e}")
        sys.exit(1)

    # 读取汇总指标
    summary = {}
    if summary_file.exists():
        try:
            sdf = pd.read_csv(summary_file)
            if not sdf.empty:
                summary = sdf.iloc[0].to_dict()
        except Exception:
            pass

    # 读取基准数据
    benchmark_df = None
    if benchmark_file.exists():
        try:
            benchmark_df = pd.read_csv(benchmark_file, parse_dates=["date"])
            benchmark_df = benchmark_df.sort_values("date").reset_index(drop=True)
        except Exception:
            pass

    # 读取交易记录
    trades_df = None
    if trades_file.exists():
        try:
            trades_df = pd.read_csv(trades_file, parse_dates=["datetime"])
        except Exception:
            pass

    # ── 计算衍生指标 ──────────────────────────────────────────────
    init_cap = float(summary.get("init_capital", daily_df["total_asset"].iloc[0]))

    # 策略累计收益率序列
    daily_df["cum_return"] = (daily_df["total_asset"] / init_cap - 1) * 100

    # 回撤序列
    rolling_max = daily_df["total_asset"].cummax()
    daily_df["drawdown"] = (daily_df["total_asset"] - rolling_max) / rolling_max * 100

    # 基准累计收益率
    if benchmark_df is not None and "close" in benchmark_df.columns:
        bm_start = benchmark_df["close"].iloc[0]
        benchmark_df["cum_return"] = (benchmark_df["close"] / bm_start - 1) * 100

    # ── 全局样式 ──────────────────────────────────────────────────
    plt.style.use("dark_background")
    plt.rcParams.update({
        "font.sans-serif": ["Arial Unicode MS", "PingFang SC", "Microsoft YaHei",
                            "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.family": "sans-serif",
        "axes.facecolor": "#2d2d2d",
        "figure.facecolor": "#1e1e1e",
        "axes.edgecolor": "#555555",
        "axes.labelcolor": "#a0a0a0",
        "xtick.color": "#888888",
        "ytick.color": "#888888",
        "grid.color": "#3a3a3a",
        "grid.linestyle": "--",
        "grid.linewidth": 0.5,
    })

    fig = plt.figure(figsize=(16, 12), facecolor="#1e1e1e")
    fig.suptitle(
        f"回测结果  {result_path.name}",
        fontsize=13, color="#e8e8e8", y=0.98,
    )

    gs = gridspec.GridSpec(
        3, 2,
        figure=fig,
        hspace=0.45, wspace=0.35,
        left=0.07, right=0.97, top=0.93, bottom=0.07,
    )

    ax_curve  = fig.add_subplot(gs[0, :])   # 第1行：资产/收益曲线（跨两列）
    ax_dd     = fig.add_subplot(gs[1, :])   # 第2行：回撤曲线（跨两列）
    ax_dist   = fig.add_subplot(gs[2, 0])   # 第3行左：日收益分布
    ax_heatmap = fig.add_subplot(gs[2, 1])  # 第3行右：月度收益热力图

    dates = daily_df["date"]

    # ── 图1：累计收益曲线 ─────────────────────────────────────────
    ax_curve.plot(dates, daily_df["cum_return"],
                  color="#4fc3f7", linewidth=1.5, label="策略")
    if benchmark_df is not None:
        # 对齐日期
        bm_merged = pd.merge(daily_df[["date"]], benchmark_df[["date", "cum_return"]],
                             on="date", how="left")
        ax_curve.plot(bm_merged["date"], bm_merged["cum_return"],
                      color="#ffb74d", linewidth=1.2, linestyle="--", label="基准", alpha=0.8)
    ax_curve.axhline(0, color="#555555", linewidth=0.8)
    ax_curve.set_title("累计收益率 (%)", color="#e8e8e8", fontsize=11, pad=8)
    ax_curve.set_ylabel("%", color="#a0a0a0", fontsize=9)
    ax_curve.legend(loc="upper left", fontsize=9,
                    facecolor="#2d2d2d", edgecolor="#555555", labelcolor="#e8e8e8")
    ax_curve.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_curve.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax_curve.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    ax_curve.grid(True)

    # 标注关键指标
    total_ret  = float(summary.get("total_return",  daily_df["cum_return"].iloc[-1]))
    annual_ret = float(summary.get("annual_return", 0))
    max_dd     = float(summary.get("max_drawdown",  0))

    # 读取新增评估指标（兼容旧版本 summary.csv）
    def _safe_float(val):
        """安全转换为 float，None/空/NaN 返回 None"""
        try:
            if val is None or str(val).strip() in ('', 'nan', 'None'):
                return None
            return float(val)
        except (ValueError, TypeError):
            return None

    sharpe      = _safe_float(summary.get("sharpe_ratio"))
    sortino     = _safe_float(summary.get("sortino_ratio"))
    volatility  = _safe_float(summary.get("volatility"))
    alpha       = _safe_float(summary.get("alpha"))
    beta        = _safe_float(summary.get("beta"))
    win_rate    = _safe_float(summary.get("win_rate"))
    pl_ratio    = _safe_float(summary.get("profit_loss_ratio"))

    def _fmt_metric(label, val, fmt=".2f", suffix="", sign=False):
        if val is None:
            return f"{label}: N/A"
        fmt_str = f"{val:+{fmt}}" if sign else f"{val:{fmt}}"
        return f"{label}: {fmt_str}{suffix}"

    line1 = (f"总收益 {total_ret:+.2f}%   "
             f"年化 {annual_ret:+.2f}%   "
             f"最大回撤 -{max_dd:.2f}%")
    line2_parts = [
        _fmt_metric("夏普", sharpe, ".2f", sign=True),
        _fmt_metric("索提诺", sortino, ".2f", sign=True),
        _fmt_metric("波动率", volatility * 100 if volatility is not None else None, ".2f", "%"),
    ]
    line3_parts = [
        _fmt_metric("Alpha", alpha, ".4f", sign=True),
        _fmt_metric("Beta", beta, ".4f"),
        _fmt_metric("胜率", win_rate, ".1f", "%"),
        _fmt_metric("盈亏比", pl_ratio, ".2f"),
    ]
    info_text = f"{line1}\n{'   '.join(line2_parts)}\n{'   '.join(line3_parts)}"
    ax_curve.text(
        0.01, 0.03, info_text,
        transform=ax_curve.transAxes,
        fontsize=8.5, color="#cccccc",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#333333", alpha=0.7),
        verticalalignment="bottom",
    )

    # 标注买卖点
    if trades_df is not None and not trades_df.empty:
        for _, trow in trades_df.iterrows():
            try:
                tdt = pd.to_datetime(trow["datetime"])
                action = str(trow.get("action", "")).lower()
                # 找最近的 daily 点
                idx = (daily_df["date"] - tdt).abs().idxmin()
                y_val = daily_df.loc[idx, "cum_return"]
                if "buy" in action:
                    ax_curve.scatter(tdt, y_val, marker="^", color="#ef5350",
                                     s=60, zorder=5)
                elif "sell" in action:
                    ax_curve.scatter(tdt, y_val, marker="v", color="#66bb6a",
                                     s=60, zorder=5)
            except Exception:
                pass

    # ── 图2：回撤曲线 ─────────────────────────────────────────────
    ax_dd.fill_between(dates, daily_df["drawdown"], 0,
                       color="#ef5350", alpha=0.5, label="回撤")
    ax_dd.plot(dates, daily_df["drawdown"],
               color="#ef5350", linewidth=0.8)
    ax_dd.set_title("回撤 (%)", color="#e8e8e8", fontsize=11, pad=8)
    ax_dd.set_ylabel("%", color="#a0a0a0", fontsize=9)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_dd.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax_dd.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    ax_dd.grid(True)
    ax_dd.text(
        0.01, 0.05,
        f"最大回撤 -{max_dd:.2f}%",
        transform=ax_dd.transAxes,
        fontsize=9, color="#ef9a9a",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#333333", alpha=0.7),
    )

    # ── 图3：日收益率分布 ─────────────────────────────────────────
    returns = daily_df["daily_return"].dropna() * 100
    if len(returns) > 1:
        n_bins = min(40, max(10, len(returns) // 3))
        pos_ret = returns[returns >= 0]
        neg_ret = returns[returns < 0]
        if len(pos_ret):
            ax_dist.hist(pos_ret, bins=n_bins, color="#ef5350", alpha=0.75,
                         label="正收益", edgecolor="none")
        if len(neg_ret):
            ax_dist.hist(neg_ret, bins=n_bins, color="#66bb6a", alpha=0.75,
                         label="负收益", edgecolor="none")
        ax_dist.axvline(0, color="#888888", linewidth=1)
        ax_dist.axvline(returns.mean(), color="#ffb74d", linewidth=1.2,
                        linestyle="--", label=f"均值 {returns.mean():.3f}%")
    ax_dist.set_title("日收益率分布", color="#e8e8e8", fontsize=11, pad=8)
    ax_dist.set_xlabel("%", color="#a0a0a0", fontsize=9)
    ax_dist.set_ylabel("频次", color="#a0a0a0", fontsize=9)
    ax_dist.legend(loc="upper right", fontsize=8,
                   facecolor="#2d2d2d", edgecolor="#555555", labelcolor="#e8e8e8")
    ax_dist.grid(True)

    # ── 图4：月度收益热力图 ───────────────────────────────────────
    try:
        daily_df["year"]  = daily_df["date"].dt.year
        daily_df["month"] = daily_df["date"].dt.month
        monthly = (
            daily_df.groupby(["year", "month"])["daily_return"]
            .apply(lambda x: (1 + x).prod() - 1)
            .reset_index()
        )
        monthly["return_pct"] = monthly["daily_return"] * 100
        pivot = monthly.pivot(index="year", columns="month", values="return_pct")
        pivot.columns = ["1月","2月","3月","4月","5月","6月",
                         "7月","8月","9月","10月","11月","12月"][:len(pivot.columns)]
        # 补全12列
        all_months = ["1月","2月","3月","4月","5月","6月",
                      "7月","8月","9月","10月","11月","12月"]
        for m in all_months:
            if m not in pivot.columns:
                pivot[m] = np.nan
        pivot = pivot[all_months]

        vmax = max(abs(pivot.values[~np.isnan(pivot.values)]).max(), 0.01) if pivot.notna().any().any() else 1
        im = ax_heatmap.imshow(
            pivot.values, cmap="RdYlGn", aspect="auto",
            vmin=-vmax, vmax=vmax,
        )
        ax_heatmap.set_xticks(range(12))
        ax_heatmap.set_xticklabels(all_months, fontsize=7, color="#a0a0a0")
        ax_heatmap.set_yticks(range(len(pivot.index)))
        ax_heatmap.set_yticklabels([str(y) for y in pivot.index], fontsize=8, color="#a0a0a0")
        # 在格子中写数值
        for r_idx in range(pivot.shape[0]):
            for c_idx in range(pivot.shape[1]):
                val = pivot.values[r_idx, c_idx]
                if not np.isnan(val):
                    ax_heatmap.text(
                        c_idx, r_idx, f"{val:.1f}",
                        ha="center", va="center",
                        fontsize=6.5,
                        color="#111111" if abs(val) > vmax * 0.4 else "#e8e8e8",
                    )
        fig.colorbar(im, ax=ax_heatmap, fraction=0.03, pad=0.04,
                     label="月收益率 (%)").ax.yaxis.label.set_color("#a0a0a0")
    except Exception as e:
        ax_heatmap.text(0.5, 0.5, f"热力图生成失败\n{e}",
                        transform=ax_heatmap.transAxes,
                        ha="center", va="center", color="#888888", fontsize=9)
    ax_heatmap.set_title("月度收益热力图 (%)", color="#e8e8e8", fontsize=11, pad=8)

    # ── 输出 ──────────────────────────────────────────────────────
    save_path = getattr(args, "save", None)
    if save_path:
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        _ok(f"图表已保存：{out.resolve()}")
    else:
        plt.show()


# ──────────────────────────────────────────────────────────────────
# 任务 2：argparse 解析器构建
# ──────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bt_cli",
        description="回测模块 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型用法示例：
  列出所有策略：
    python bt_cli.py list

  使用配置文件默认参数运行回测：
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt

  增量回测（指定日期范围）：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --start 20240101 --end 20241231 --capital 500000

  启用初始化数据：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --init-data

  详细日志模式：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt -v
  查看回测结果列表：
    python bt_cli.py results

  查看结果并展示交易明细：
    python bt_cli.py results --detail

  查看全部历史回测结果：
    python bt_cli.py results --limit 0

  绘制最新回测结果图表：
    python bt_cli.py plot

  保存图表到文件：
    python bt_cli.py plot --save result.png
        """,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出详细日志（含 INFO 级别）",
    )

    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = False

    # ── list ──────────────────────────────────────────────────────
    sub.add_parser(
        "list",
    help="列出 strategy/ 目录下的策略文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型用法示例：
  python bt_cli.py list
        """,
    )

    # ── run ───────────────────────────────────────────────────────
    p_run = sub.add_parser(
        "run",
        help="运行回测（传入 .qmt 配置文件，支持参数覆盖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
参数覆盖说明：
  CLI 参数会覆盖 .qmt 配置文件中的对应字段，未指定的参数保持配置文件原值。

典型用法示例：
  使用配置文件默认参数运行：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt

  覆盖回测区间：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --start 20240101 --end 20241231

  覆盖初始资金：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --capital 500000

  覆盖基准指数：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --benchmark sh.000001

  覆盖触发类型：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --trigger 1d

  覆盖策略文件：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --strategy strategy/ZTSXP/ZTSXP.py

  启动时自动下载历史数据：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --init-data

  详细日志模式（输出所有 INFO 日志）：
    python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt -v
        """,
    )
    p_run.add_argument(
        "config",
        metavar="配置文件",
        help="策略配置文件路径（.qmt 格式，如 strategy/ZTSXP/ZTSXP.qmt）",
    )
    p_run.add_argument(
        "--strategy", metavar="策略文件",
        help="覆盖策略文件路径（.py），不指定则使用配置文件中的 strategy_file",
    )
    p_run.add_argument(
        "--start", metavar="YYYYMMDD",
        help="覆盖回测开始日期（如 20240101）",
    )
    p_run.add_argument(
        "--end", metavar="YYYYMMDD",
        help="覆盖回测结束日期（如 20241231）",
    )
    p_run.add_argument(
        "--capital", metavar="金额", type=float,
        help="覆盖初始资金（元，如 1000000）",
    )
    p_run.add_argument(
        "--benchmark", metavar="代码",
        help="覆盖基准指数代码（如 sh.000300）",
    )
    p_run.add_argument(
        "--trigger", metavar="类型",
        choices=["tick", "1m", "5m", "15m", "30m", "60m", "1d", "custom"],
        help="覆盖触发类型：tick / 1m / 5m / 15m / 30m / 60m / 1d / custom",
    )
    p_run.add_argument(
        "--init-data",
        action="store_true",
        dest="init_data",
        help="启动时自动下载历史数据到 miniQMT（默认关闭）",
    )
    p_run.add_argument(
        "--risk-free-rate",
        metavar="利率",
        type=float,
        dest="risk_free_rate",
        help="无风险利率（小数形式，如 0.03 表示 3%%），用于计算夏普/索提诺等指标；"
             "优先级高于 .qmt 配置文件，不指定则使用配置文件值或默认值 0.03",
    )

    # ── plot ────────────────────────────────────────────────────
    p_plot = sub.add_parser(
        "plot",
        help="绘制回测结果图表（资产曲线、回撤、收益分布、月度热力图）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型用法示例：
  绘制最新回测结果图表（弹窗显示）：
    python bt_cli.py plot

  绘制指定结果目录的图表：
    python bt_cli.py plot backtest_results/strategy_xxx_20250101_20250703

  保存图表到文件（不弹窗）：
    python bt_cli.py plot --save result.png

  指定目录并保存：
    python bt_cli.py plot backtest_results/strategy_xxx --save charts/result.png
        """,
    )
    p_plot.add_argument(
        "result_dir",
        nargs="?",
        metavar="结果目录",
        help="回测结果目录路径（不指定则使用最新结果）",
    )
    p_plot.add_argument(
        "--save",
        metavar="文件路径",
        help="将图表保存到指定文件（支持 .png / .pdf / .svg），不指定则弹窗显示",
    )

    # ── results ───────────────────────────────────────────────────
    p_res = sub.add_parser(
        "results",
        help="查看本地回测结果汇总",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型用法示例：
  查看最近 20 条回测结果（默认）：
    python bt_cli.py results

  查看结果并展示交易明细（前5条）：
    python bt_cli.py results --detail

  查看全部历史回测结果：
    python bt_cli.py results --limit 0

  查看最近 5 条：
    python bt_cli.py results --limit 5
        """,
    )
    p_res.add_argument(
        "--detail",
        action="store_true",
        help="展示每条结果的交易记录前5条",
    )
    p_res.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="展示条数，0 表示全量（默认 20）",
    )

    return parser


# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────

_COMMAND_MAP = {
    "list":    cmd_list,
    "run":     cmd_run,
    "results": cmd_results,
    "plot":    cmd_plot,
}


def main():
    parser = _build_parser()
    args   = parser.parse_args()
    _setup_logging(verbose=getattr(args, "verbose", False))

    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(0)

    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        _err(f"未知命令：{args.command}")
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except KeyboardInterrupt:
        print()
        _warn("已被用户中断（Ctrl+C）")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"命令执行失败：{e}")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
