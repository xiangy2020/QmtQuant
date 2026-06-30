# -*- coding: utf-8 -*-
"""
dm_cli/common.py — 公共基础设施

包含：颜色常量、日志输出函数、CliCallbacks、GHOST_SYMBOLS、公共工具函数。
所有子命令模块统一从此模块 import，禁止重复定义。
"""

import logging
import sys

# ──────────────────────────────────────────────────────────────────
# 颜色常量 & 日志输出函数
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
# 幽灵标的（Ghost Symbol）硬编码过滤集合
# open_date 和 expire_date 均为空的非股票合约，共 22 只（截至 2026-05-24 排查）
# ──────────────────────────────────────────────────────────────────

GHOST_SYMBOLS = frozenset([
    '000584.SZ', '000622.SZ', '000627.SZ', '000851.SZ',
    '002231.SZ', '002336.SZ', '002750.SZ',
    '300208.SZ', '300280.SZ', '300344.SZ', '300379.SZ', '300391.SZ',
    '600190.SH', '600200.SH', '600355.SH', '600387.SH', '600462.SH', '600804.SH',
    '601989.SH', '603003.SH', '603056.SH', '603388.SH',
])


# ──────────────────────────────────────────────────────────────────
# CLI 回调（将 DataService 回调输出到终端）
# ──────────────────────────────────────────────────────────────────

class CliCallbacks:
    """将 DataService 回调输出到终端"""

    def __init__(self, show_progress: bool = True):
        self._show_progress = show_progress
        self._last_pct = -1

    def on_progress(self, done: int, total: int) -> None:
        if not self._show_progress or total <= 0:
            return
        pct = int(done / total * 100)
        if pct != self._last_pct and (pct % 5 == 0 or pct >= 100):
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {pct:3d}%  {done}/{total}", end="", flush=True)
            self._last_pct = pct
            if pct >= 100:
                print()  # 换行

    def on_log(self, message: str) -> None:
        _info(message)

    def on_error(self, error: str) -> None:
        _err(error)

    def on_done(self, result: dict) -> None:
        pass  # 由各命令函数自行处理 result


# ──────────────────────────────────────────────────────────────────
# 公共工具函数
# ──────────────────────────────────────────────────────────────────

def _load_service():
    """懒加载 DataService，失败时给出友好提示"""
    try:
        from data_manager.data_service import DataService
        return DataService()
    except ImportError as e:
        _err(f"无法导入 DataService：{e}")
        _err("请确认 data_service.py 在当前目录或 PYTHONPATH 中")
        sys.exit(1)


def _resolve_sector(service, sector_name: str) -> list:
    """
    从本地 Parquet 缓存读取板块，返回成分股代码列表。
    失败时打印错误并退出。
    自动过滤幽灵标的（GHOST_SYMBOLS）。
    """
    items = service.get_sector(sector_name)
    if not items:
        _err(f"板块「{sector_name}」为空或不存在")
        _err("请先同步板块数据：python dm_cli.py sync --asset industry --sub members")
        _err(f"或检查 ~/.qmtquant/cache/industry/members/{sector_name}.parquet 是否存在")
        sys.exit(1)
    # items 格式为 [[code, name], ...]，提取 code
    symbols = [item[0] if isinstance(item, (list, tuple)) else item for item in items]
    # 过滤幽灵标的
    filtered = [s for s in symbols if s not in GHOST_SYMBOLS]
    removed = len(symbols) - len(filtered)
    if removed > 0:
        ghost_list = [s for s in symbols if s in GHOST_SYMBOLS]
        _warn(f"已过滤 {removed} 只幽灵标的：{ghost_list}")
    return filtered


def _resolve_symbols(args, service) -> tuple:
    """
    从 --sector 或 --symbols 解析股票代码列表，返回 (symbols, source_label)。

    互斥校验：同时传 --sector 和 --symbols 则报错退出。
    空值校验：两者均未传则报错退出。
    --symbols 路径：按逗号分割、去除首尾空格、过滤空串；超过 5 只时 label 截断显示前 3 只。
    --sector 路径：复用 _resolve_sector 逻辑。
    """
    sector = getattr(args, 'sector', None)
    symbols_str = getattr(args, 'symbols', None)

    # 互斥校验
    if sector and symbols_str:
        _err("--sector 和 --symbols 不能同时使用")
        sys.exit(1)

    # 空值校验
    if not sector and not symbols_str:
        _err("必须指定 --sector 或 --symbols 之一")
        sys.exit(1)

    # --symbols 路径
    if symbols_str is not None:
        # 空字符串校验
        if not symbols_str.strip():
            _err("--symbols 不能为空")
            sys.exit(1)
        symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
        if not symbols:
            _err("--symbols 不能为空")
            sys.exit(1)
        # 过滤幽灵标的
        filtered = [s for s in symbols if s not in GHOST_SYMBOLS]
        removed = len(symbols) - len(filtered)
        if removed > 0:
            ghost_list = [s for s in symbols if s in GHOST_SYMBOLS]
            _warn(f"已过滤 {removed} 只幽灵标的：{ghost_list}")
        symbols = filtered
        n = len(symbols)
        if n > 5:
            preview = ', '.join(symbols[:3])
            source_label = f"代码：{preview} 等 {n} 只"
        else:
            preview = ', '.join(symbols)
            source_label = f"代码：{preview}（{n} 只）"
        return symbols, source_label

    # --sector 路径
    symbols = _resolve_sector(service, sector)
    source_label = f"板块：{sector}（{len(symbols)} 只）"
    return symbols, source_label


def _parse_periods(period_str: str) -> list:
    """将逗号分隔的周期字符串解析为列表，如 '1d,1m' → ['1d', '1m']"""
    valid = {'tick', '1m', '5m', '15m', '30m', '60m', '1d'}
    periods = [p.strip() for p in period_str.split(',') if p.strip()]
    invalid = [p for p in periods if p not in valid]
    if invalid:
        _err(f"不支持的数据周期：{invalid}，有效值：{sorted(valid)}")
        sys.exit(1)
    return periods
