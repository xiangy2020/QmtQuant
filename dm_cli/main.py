"""
dm_cli/main.py
──────────────
CLI 主入口：注册所有子命令解析器，分发到各子命令模块。
"""
from __future__ import annotations

import argparse
import sys

from dm_cli.common import _setup_logging, _err, _warn
from dm_cli.cmd_stats import cmd_stats
from dm_cli.cmd_validate import cmd_validate
from dm_cli.cmd_clear import cmd_clear
from dm_cli.cmd_sync import cmd_sync, _sync_list_categories
from dm_cli.cmd_download import cmd_download, cmd_scan_gaps
from dm_cli.cmd_schedule import cmd_schedule
from dm_cli.cmd_monitor import cmd_monitor
from dm_cli.cmd_data_api import cmd_data_api


# ──────────────────────────────────────────────────────────────────
# 命令分发表
# ──────────────────────────────────────────────────────────────────

_COMMAND_MAP = {
    'stats':      cmd_stats,
    'validate':   cmd_validate,
    'clear':      cmd_clear,
    'sync':       cmd_sync,
    'download':    cmd_download,
    'scan-gaps':  cmd_scan_gaps,
    'schedule':   cmd_schedule,
    'monitor':    cmd_monitor,
    'data-api':   cmd_data_api,
}


# ──────────────────────────────────────────────────────────────────
# 解析器构建
# ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dm_cli",
        description="数据管理模块 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python dm_cli.py stats
  python dm_cli.py --list

  # ── 股票数据 ──────────────────────────────────────────────────────
  python dm_cli.py sync --asset stock --sub kline --sector 沪深300 --period 1d --start 20240101
  python dm_cli.py sync --asset stock --sub calendar,instrument
  python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d
  python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode full --start 20240101
  python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode gap
  python dm_cli.py validate --asset stock --sub kline --sector 沪深300 --period 1d

  # ── 行业概念数据 ──────────────────────────────────────────────────
  python dm_cli.py sync --asset industry
  python dm_cli.py sync --asset stock,industry --sector 沪深300 --period 1d

  # ── 指数数据 ──────────────────────────────────────────────────────
  python dm_cli.py sync --asset index --sub instrument                          # 同步指数基础信息（默认板块：沪深指数）
  python dm_cli.py sync --asset index --sub instrument --sector 上证指数         # 指定板块
  python dm_cli.py download --asset index --sub kline --period 1d              # 增量下载指数 K 线
  python dm_cli.py download --asset index --sub kline --period 1d --mode full --start 20100101
  python dm_cli.py sync --asset index --sub kline --period 1d                   # 同步指数 K 线到 Parquet
  python dm_cli.py sync --asset index --sub kline --period 1d --mode smart      # 智能同步
  python dm_cli.py validate --asset index --sub kline --period 1d               # 健康检查

  # ── 其他 ──────────────────────────────────────────────────────────
  python dm_cli.py clear --symbol 600000.SH --period 1d
  python dm_cli.py clear --all
  python dm_cli.py scan-gaps --asset stock --sub kline --sector 沪深300 --period 1d --detail        """,
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='输出详细日志')
    parser.add_argument('--list', action='store_true', default=False, help='展示已启用品类体系表格后退出')

    sub = parser.add_subparsers(dest='command', metavar='命令')
    sub.required = False

    # ── stats ──────────────────────────────────────────────────────
    from data_manager.asset_types import ENABLED_ASSET_TYPES as _EAT_S
    _stats_category_lines = []
    for _at in _EAT_S:
        _stats_category_lines.append(
            f"  {_at.asset_type}（{_at.display_name}）"
        )
        for _st in _at.sub_types:
            _stats_category_lines.append(
                f"    └─ {_at.asset_type}/{_st.sub_type}"
                f"  {_st.display_name}"
                + (f"  — {_st.description}" if _st.description else "")
            )
    _stats_asset_ids = ', '.join(at.asset_type for at in _EAT_S)
    _stats_epilog = (
        "已启用品类及子类（可用于 --asset / --sub 参数）：\n"
        + "\n".join(_stats_category_lines)
        + "\n\n典型用法示例：\n"
        "  查看整体缓存统计：\n"
        "    python dm_cli.py stats\n\n"
        "  查看 stock/kline 数据明细（默认展示前50条）：\n"
        "    python dm_cli.py stats --asset stock --sub kline\n\n"
        "  按周期过滤 kline 明细：\n"
        "    python dm_cli.py stats --asset stock --sub kline --period 1d\n\n"
        "  查看指定股票代码的 kline 明细：\n"
        "    python dm_cli.py stats --asset stock --sub kline --symbols 000001.SZ,600000.SH\n\n"
        "  查看 stock/instrument 合约信息明细（全量）：\n"
        "    python dm_cli.py stats --asset stock --sub instrument --limit 0\n\n"
        "  查看 industry/members 成分股明细：\n"
        "    python dm_cli.py stats --asset industry --sub members\n\n"
        "  查看 industry/sector_list 板块列表：\n"
        "    python dm_cli.py stats --asset industry --sub sector_list\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_stats = sub.add_parser(
        'stats',
        help='查看本地缓存统计信息',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_stats_epilog,
    )
    p_stats.add_argument(
        '--asset', metavar='品类', default=None,
        help=f'一级品类（不指定则显示整体统计）。可用值：{_stats_asset_ids}',
    )
    p_stats.add_argument(
        '--sub', metavar='子类', default=None,
        help='二级子类（不指定默认 kline）。可用值见下方品类列表',
    )
    p_stats.add_argument(
        '--period', dest='detail_period', default=None, metavar='周期',
        help='过滤 kline 子类的周期，如 1d'
    )
    p_stats.add_argument(
        '--symbols', metavar='代码列表', default=None,
        help='股票代码，多个用英文逗号分隔，如 000001.SZ,600000.SH（仅 kline 子类有效）',
    )
    p_stats.add_argument(
        '--limit', dest='detail_limit', type=int, default=50, metavar='N',
        help='展示条数，0 或 -1 表示全量（默认 50）'
    )

    # ── validate ───────────────────────────────────────────────────
    from data_manager.asset_types import ENABLED_ASSET_TYPES as _EAT_VAL
    _val_category_lines = []
    for _at in _EAT_VAL:
        _val_category_lines.append(
            f"  {_at.asset_type}（{_at.display_name}）"
        )
        for _st in _at.sub_types:
            _val_category_lines.append(
                f"    └─ {_at.asset_type}/{_st.sub_type}"
                f"  {_st.display_name}"
                + (f"  — {_st.description}" if _st.description else "")
            )
    _val_asset_ids = ', '.join(at.asset_type for at in _EAT_VAL)
    _val_epilog = (
        "已启用品类及子类（可用于 --asset / --sub 参数）：\n"
        + "\n".join(_val_category_lines)
        + "\n\n"
        "典型用法示例：\n"
        "  全面健康检查（默认 stock/kline）：\n"
        "    python dm_cli.py validate --asset stock --sub kline --sector 沪深300 --period 1d\n\n"
        "  直接指定股票代码（无需板块）：\n"
        "    python dm_cli.py validate --symbols 000001.SZ,600000.SH --period 1d\n\n"
        "  显示每只问题股票的详细信息：\n"
        "    python dm_cli.py validate --asset stock --sub kline --sector 沪深300 --period 1d --detail\n\n"
        "  省略 --asset/--sub（默认 stock/kline）：\n"
        "    python dm_cli.py validate --sector 沪深300 --period 1d\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_val = sub.add_parser(
        'validate',
        help='对板块成分股执行全面数据健康检查',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_val_epilog,
    )
    p_val.add_argument(
        '--asset', metavar='品类', default=None,
        help=f'一级品类（不指定默认 stock）。可用值：{_val_asset_ids}',
    )
    p_val.add_argument(
        '--sub', metavar='子类', default=None,
        help='二级子类（不指定默认 kline）',
    )
    p_val.add_argument('--sector', metavar='板块名', default=None, help='板块名称（与 --symbols 互斥）')
    p_val.add_argument(
        '--symbols', metavar='代码列表', default=None,
        help='股票代码，多个用英文逗号分隔，如 000001.SZ,600000.SH（与 --sector 互斥）',
    )
    p_val.add_argument('--period', metavar='周期', default=None, help='数据周期，如 1d（kline 子类时必填）')
    p_val.add_argument('--detail', action='store_true', help='显示每只问题股票的详细信息')

    # ── clear ──────────────────────────────────────────────────────
    _clr_epilog = (
        "典型用法示例：\n"
        "  清除单只股票指定周期的缓存：\n"
        "    python dm_cli.py clear --symbol 600000.SH --period 1d\n\n"
        "  清除单只股票所有周期的缓存：\n"
        "    python dm_cli.py clear --symbol 600000.SH\n\n"
        "  清空全部缓存（需输入 yes 二次确认）：\n"
        "    python dm_cli.py clear --all\n\n"
        "  精准清理日期异常数据（按板块）：\n"
        "    python dm_cli.py clear --date-anomaly --sector 沪深A股 --period 1d\n\n"
        "  精准清理日期异常数据（指定代码）：\n"
        "    python dm_cli.py clear --date-anomaly --symbols 000001.SZ,600000.SH --period 1d\n\n"
        "  精准清理日期异常数据（全量缓存，跳过确认）：\n"
        "    python dm_cli.py clear --date-anomaly --yes\n\n"
        "  删除上市日期缺失标的的缓存文件（按板块）：\n"
        "    python dm_cli.py clear --no-open-date --sector 沪深A股 --period 1d\n\n"
        "  删除上市日期缺失标的的缓存文件（指定代码）：\n"
        "    python dm_cli.py clear --no-open-date --symbols 000001.SZ,600000.SH\n\n"
        "  删除上市日期缺失标的的缓存文件（全量缓存，跳过确认）：\n"
        "    python dm_cli.py clear --no-open-date --yes\n"
    )
    p_clr = sub.add_parser(
        'clear',
        help='清空缓存（全部、指定股票、日期异常数据或上市日期缺失标的）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_clr_epilog,
    )
    p_clr_grp = p_clr.add_mutually_exclusive_group(required=True)
    p_clr_grp.add_argument('--all', action='store_true', help='清空全部缓存（需二次确认）')
    p_clr_grp.add_argument('--symbol', metavar='代码', help='清除指定股票的缓存')
    p_clr_grp.add_argument(
        '--date-anomaly', action='store_true', dest='date_anomaly',
        help='精准清理日期异常数据（删除早于 A 股开市日 1990-12-19 的脏数据行，保留正常数据）',
    )
    p_clr_grp.add_argument(
        '--no-open-date', action='store_true', dest='no_open_date',
        help='删除上市日期缺失标的的整个缓存文件（需配合 --period 或不指定则删除所有周期）',
    )
    p_clr.add_argument('--period', metavar='周期', default=None, help='指定周期（不指定则清除所有周期）')
    p_clr.add_argument(
        '--sector', metavar='板块名', default=None,
        help='板块名称（配合 --date-anomaly / --no-open-date 使用，与 --symbols 互斥）',
    )
    p_clr.add_argument(
        '--symbols', metavar='代码列表', default=None,
        help='股票代码，多个用英文逗号分隔（配合 --date-anomaly / --no-open-date 使用，与 --sector 互斥）',
    )
    p_clr.add_argument('--yes', action='store_true', help='跳过二次确认直接执行（用于脚本自动化）')

    # ── sync ───────────────────────────────────────────────────────
    from data_manager.asset_types import ENABLED_ASSET_TYPES as _EAT
    _asset_ids   = ', '.join(at.asset_type for at in _EAT)
    _sub_example = 'kline, calendar, instrument, sector_list, members'
    _sync_epilog = (
        "已启用品类及子类：\n"
        + "\n".join(
            f"  {at.asset_type}（{at.display_name}）: "
            + ", ".join(f"{st.sub_type}（{st.display_name}）" for st in at.sub_types)
            for at in _EAT
        )
        + "\n\n同步模式说明（--mode）：\n"
        "  full        全量：全量覆盖写指定日期范围内的数据（默认，保持现有行为）\n"
        "  smart       智能：先 validate 扫描 Parquet 缓存健康状况，再只同步真正缺失的部分\n\n"
        "典型用法示例：\n"
        "  同步全量（所有已启用品类）：\n"
        "    python dm_cli.py sync\n\n"
        "  同步 K 线行情（全量模式，默认）：\n"
        "    python dm_cli.py sync --asset stock --sub kline --sector 沪深300 --period 1d\n\n"
        "  直接指定股票代码同步（无需板块）：\n"
        "    python dm_cli.py sync --asset stock --sub kline --symbols 000001.SZ,600000.SH --period 1d\n\n"
        "  智能同步（先 validate 再精准补写缺失部分）：\n"
        "    python dm_cli.py sync --asset stock --sub kline --sector 沪深300 --period 1d --mode smart\n\n"
        "  智能同步（跳过确认直接执行）：\n"
        "    python dm_cli.py sync --asset stock --sub kline --sector 沪深300 --period 1d --mode smart --yes\n\n"
        "  同步辅助数据（交易日历 + 合约信息）：\n"
        "    python dm_cli.py sync --asset stock --sub calendar,instrument\n\n"
        "  同步行业概念数据：\n"
        "    python dm_cli.py sync --asset industry\n\n"
        "  同步 stock 全部子类（含 kline）：\n"
        "    python dm_cli.py sync --asset stock --sector 沪深300 --period 1d\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_sync = sub.add_parser(
        'sync',
        help='数据同步（支持按一级品类/二级子类灵活选择）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_sync_epilog,
    )
    p_sync.add_argument(
        '--asset', metavar='品类', default=None,
        help=f'一级品类，多个用逗号分隔（不指定则同步所有已启用品类）。可用值：{_asset_ids}',
    )
    p_sync.add_argument(
        '--sub', metavar='子类', default=None,
        help=f'二级子类，多个用逗号分隔（不指定则同步该品类所有子类）。可用值：{_sub_example}',
    )
    p_sync.add_argument(
        '--sector', metavar='板块名', default=None,
        help='板块名称（同步 kline 子类时与 --symbols 二选一；同步 instrument 子类时可选）',
    )
    p_sync.add_argument(
        '--symbols', metavar='代码列表', default=None,
        help='股票代码，多个用英文逗号分隔，如 000001.SZ,600000.SH（与 --sector 互斥）',
    )
    p_sync.add_argument(
        '--period', metavar='周期', default=None,
        help='数据周期，多个用逗号分隔，如 1d,1m（同步 kline 子类时必填）',
    )
    p_sync.add_argument('--start', metavar='YYYYMMDD', default=None, help='起始日期（默认 19900101，仅 kline full 模式）')
    p_sync.add_argument('--end', metavar='YYYYMMDD', default=None, help='结束日期（默认最新，仅 kline）')
    p_sync.add_argument(
        '--mode', metavar='模式', default='full', choices=['full', 'smart'],
        help='同步模式：full（全量覆盖写，默认）/ smart（先 validate 再精准同步缺失部分）',
    )
    p_sync.add_argument(
        '--yes', '-y', action='store_true',
        help='smart 模式下跳过确认直接执行',
    )
    p_sync.add_argument(
        '--batch-size', metavar='N', type=int, default=0,
        help='每批同步股票数量（默认 0 表示不分批，建议 500~1000）',
    )
    p_sync.add_argument(
        '--sectors', metavar='板块列表', default=None,
        help='指定板块名称，多个用英文逗号分隔（仅 industry/members，不指定则全量同步）',
    )

    # ── download ──────────────────────────────────────────────────
    from data_manager.asset_types import ENABLED_ASSET_TYPES as _EAT_SUPP
    _supp_asset_ids = ', '.join(at.asset_type for at in _EAT_SUPP)
    _supp_category_lines = []
    for _at in _EAT_SUPP:
        _supp_category_lines.append(f"  {_at.asset_type}（{_at.display_name}）")
        for _st in _at.sub_types:
            _supp_category_lines.append(
                f"    └─ {_at.asset_type}/{_st.sub_type}  {_st.display_name}"
                + (f"  — {_st.description}" if _st.description else "")
            )
    _supp_epilog = (
        "已启用品类及子类（可用于 --asset / --sub 参数）：\n"
        + "\n".join(_supp_category_lines)
        + "\n\n"
        "下载模式说明：\n"
        "  full        全量：强制重新下载指定日期范围内的全部数据（需指定 --start）\n"
        "  incremental 增量：从 miniQMT 本地最后一条数据往后补充（默认）\n"
        "  gap         缺口：扫描 Parquet 缓存缺口后精准下载\n"
        "  smart       智能：自动 validate → 分层 → 精准下载（一键修复所有问题）\n\n"
        "典型用法示例：\n"
        "  增量下载（默认）：\n"
        "    python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d\n\n"
        "  直接指定股票代码下载（无需板块）：\n"
        "    python dm_cli.py download --symbols 000001.SZ,600000.SH --period 1d\n\n"
        "  全量下载指定日期范围：\n"
        "    python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode full --start 20240101 --end 20241231\n\n"
        "  缺口下载：\n"
        "    python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode gap\n\n"
        "  智能下载（一键修复所有问题）：\n"
        "    python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode smart\n\n"
        "  智能下载（跳过确认）：\n"
        "    python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode smart --yes\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_supp = sub.add_parser(
        'download',
        help='数据下载（全量 / 增量 / 缺口 / 智能，下载到 miniQMT 本地）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_supp_epilog,
    )
    p_supp.add_argument(
        '--asset', metavar='品类', default=None,
        help=f'一级品类（不指定默认 stock）。可用值：{_supp_asset_ids}',
    )
    p_supp.add_argument(
        '--sub', metavar='子类', default=None,
        help='二级子类（不指定默认 kline）',
    )
    p_supp.add_argument('--sector', metavar='板块名', default=None, help='板块名称（与 --symbols 互斥）')
    p_supp.add_argument(
        '--symbols', metavar='代码列表', default=None,
        help='股票代码，多个用英文逗号分隔，如 000001.SZ,600000.SH（与 --sector 互斥）',
    )
    p_supp.add_argument('--period', metavar='周期', default=None, help='数据周期，多个用逗号分隔，如 1d,1m（kline 子类时必填）')
    p_supp.add_argument(
        '--mode', metavar='模式', default='incremental',
        choices=['full', 'incremental', 'gap', 'smart'],
        help='补充模式：full（全量）| incremental（增量，默认）| gap（缺口）| smart（智能）',
    )
    p_supp.add_argument('--start', metavar='YYYYMMDD', default=None, help='起始日期（full 模式必填；smart 模式下作为无 open_date 标的的默认起始日期）')
    p_supp.add_argument('--end', metavar='YYYYMMDD', default=None, help='结束日期（默认最新，仅 full 模式有效）')
    p_supp.add_argument('--batch-size', metavar='N', type=int, default=0, help='每批下载股票数量（默认 0 表示不分批，建议 500~1000）')
    p_supp.add_argument('--yes', '-y', action='store_true', default=False, help='smart 模式下跳过确认提示，直接执行补充')

    # ── scan-gaps ──────────────────────────────────────────────────
    _scan_epilog = (
        "已启用品类及子类（可用于 --asset / --sub 参数）：\n"
        + "\n".join(_supp_category_lines)
        + "\n\n"
        "典型用法示例：\n"
        "  扫描缺口（默认 stock/kline）：\n"
        "    python dm_cli.py scan-gaps --asset stock --sub kline --sector 沪深300 --period 1d\n\n"
        "  显示缺口明细：\n"
        "    python dm_cli.py scan-gaps --asset stock --sub kline --sector 沪深300 --period 1d --detail\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_scan = sub.add_parser(
        'scan-gaps',
        help='扫描板块数据缺口（只检测，不补充）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_scan_epilog,
    )
    p_scan.add_argument(
        '--asset', metavar='品类', default=None,
        help=f'一级品类（不指定默认 stock）。可用值：{_supp_asset_ids}',
    )
    p_scan.add_argument(
        '--sub', metavar='子类', default=None,
        help='二级子类（不指定默认 kline）',
    )
    p_scan.add_argument('--sector', metavar='板块名', default=None, help='板块名称（kline 子类时必填）')
    p_scan.add_argument('--period', metavar='周期', default=None, help='数据周期，多个用逗号分隔，如 1d,1m（kline 子类时必填）')
    p_scan.add_argument('--detail', action='store_true', help='显示缺口明细（每只股票的缺口段）')

    # ── schedule ───────────────────────────────────────────────────
    from data_manager.asset_types import ENABLED_ASSET_TYPES as _EAT_SCHED
    _sched_category_lines = []
    for _at in _EAT_SCHED:
        _sched_category_lines.append(f"  {_at.asset_type}（{_at.display_name}）")
        for _st in _at.sub_types:
            _sched_category_lines.append(
                f"    └─ {_at.asset_type}/{_st.sub_type}  {_st.display_name}"
                + (f"  — {_st.description}" if _st.description else "")
            )
    _sched_epilog = (
        "已启用品类及子类（可用于 --asset / --sub 参数）：\n"
        + "\n".join(_sched_category_lines)
        + "\n\n"
        "补充模式说明：\n"
        "  incremental 增量：从 miniQMT 本地最后一条数据往后补充（默认）\n"
        "  full        全量：强制重新下载指定日期范围内的全部数据\n"
        "  gap         缺口：扫描 Parquet 缓存缺口后精准补充\n\n"
        "典型用法示例：\n"
        "  持续调度（每个工作日 15:30 执行，Ctrl+C 停止）：\n"
        "    python dm_cli.py schedule --sector 沪深300 --period 1d --time 15:30\n\n"
        "  多周期调度：\n"
        "    python dm_cli.py schedule --sector 沪深300 --period 1d,1m --time 15:30\n\n"
        "  立即执行一次后退出：\n"
        "    python dm_cli.py schedule --sector 沪深300 --period 1d --run-now\n\n"
        "  立即执行一次后继续调度：\n"
        "    python dm_cli.py schedule --sector 沪深300 --period 1d --time 15:30 --run-now --no-exit\n\n"
        "  指定补充模式：\n"
        "    python dm_cli.py schedule --sector 沪深300 --period 1d --mode gap\n\n"
        "  查看品类体系表格：\n"
        "    python dm_cli.py --list"
    )
    p_sched = sub.add_parser(
        'schedule',
        help='定时调度数据下载（持续运行 / 立即执行一次）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_sched_epilog,
    )
    p_sched.add_argument(
        '--asset', metavar='品类', default=None,
        help='一级品类（不指定默认 stock）',
    )
    p_sched.add_argument(
        '--sub', metavar='子类', default=None,
        help='二级子类（不指定默认 kline）',
    )
    p_sched.add_argument('--sector', metavar='板块名', default=None, help='板块名称（必填）')
    p_sched.add_argument('--period', metavar='周期', default=None, help='数据周期，多个用逗号分隔，如 1d,1m（必填）')
    p_sched.add_argument('--time', metavar='HH:MM', default='15:30', help='每日执行时间，格式 HH:MM（默认 15:30）')
    p_sched.add_argument(
        '--mode', metavar='模式', default='incremental',
        choices=['full', 'incremental', 'gap'],
        help='补充模式：incremental（增量，默认）| full（全量）| gap（缺口）',
    )
    p_sched.add_argument('--run-now', action='store_true', help='立即执行一次补充任务')
    p_sched.add_argument('--no-exit', action='store_true', help='与 --run-now 配合使用，执行后继续保持调度运行')

    # ── data-api ───────────────────────────────────────────────────
    _data_api_epilog = (
        "接口列表：\n"
        "  GET /health                  健康检查（服务状态 + 缓存统计）\n"
        "  GET /api/v1/kline            K 线数据查询\n"
        "  GET /api/v1/sector           板块成分股查询\n"
        "  GET /api/v1/instruments      合约基础信息查询\n"
        "  GET /api/v1/calendar         交易日历查询\n"
        "  GET /docs                    Swagger UI 文档\n\n"
        "典型用法示例：\n"
        "  启动服务（默认端口 8765，仅本机访问）：\n"
        "    python dm_cli.py data-api\n\n"
        "  指定端口：\n"
        "    python dm_cli.py data-api --port 9000\n\n"
        "  允许局域网访问：\n"
        "    python dm_cli.py data-api --host 0.0.0.0 --port 8765\n\n"
        "  查询 K 线（启动后在浏览器或其他项目中调用）：\n"
        "    GET http://localhost:8765/api/v1/kline?symbol=600519.SH&period=1d&start=20240101\n"
    )
    p_data_api = sub.add_parser(
        'data-api',
        help='启动 HTTP API 服务，将本地缓存数据对外暴露为 REST 接口',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_data_api_epilog,
    )
    p_data_api.add_argument(
        '--host', metavar='HOST', default=None,
        help='监听地址（默认 127.0.0.1，仅本机；0.0.0.0 允许局域网访问；可通过 .env 中 DATA_API_HOST 配置）',
    )
    p_data_api.add_argument(
        '--port', metavar='PORT', type=int, default=None,
        help='监听端口（默认 8765；可通过 .env 中 DATA_API_PORT 配置）',
    )

    # ── monitor ────────────────────────────────────────────────────
    _monitor_epilog = (
        "分析类型说明（--type）：\n"
        "  overview   市场全景扫描：大盘指数 + 涨跌分布 + 量能分析 + 新高新低\n"
        "  limit-up   涨停板/个股异动：涨停 / 跌停 / 炸板 / 量价异动\n"
        "  sector     行业板块轮动：行业涨跌排名 + 近期轮动强度\n"
        "  all        全部（默认）\n\n"
        "行业分类说明（--classification）：\n"
        "  SW1    申万一级行业（28 个）（默认）\n"
        "  SW2    申万二级行业（104 个）\n"
        "  SW3    申万三级行业（227 个）\n"
        "  CSRC1  证监会一级行业（19 个）\n"
        "  CSRC2  证监会二级行业（81 个）\n\n"
        "典型用法示例：\n"
        "  生成完整市场监控报告（自动取最新交易日）：\n"
        "    python dm_cli.py monitor\n\n"
        "  指定分析日期：\n"
        "    python dm_cli.py monitor --date 20260522\n\n"
        "  只生成涨停板监控报告：\n"
        "    python dm_cli.py monitor --type limit-up --date 20260522\n\n"
        "  只生成行业轮动报告（申万一级，默认）：\n"
        "    python dm_cli.py monitor --type sector\n\n"
        "  切换为证监会一级行业分类：\n"
        "    python dm_cli.py monitor --type sector --classification CSRC1\n\n"
        "  指定股票池板块：\n"
        "    python dm_cli.py monitor --sector 沪深300\n\n"
        "  指定 HTML 输出路径：\n"
        "    python dm_cli.py monitor --output /tmp/report.html\n"
    )
    p_monitor = sub.add_parser(
        'monitor',
        help='市场行情监控分析（全景扫描 / 涨停板 / 行业轮动），生成 HTML 报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_monitor_epilog,
    )
    p_monitor.add_argument(
        '--type', metavar='类型', default='all',
        choices=['overview', 'limit-up', 'sector', 'all'],
        help='分析类型：overview / limit-up / sector / all（默认 all）',
    )
    p_monitor.add_argument(
        '--date', metavar='YYYYMMDD', default=None,
        help='分析日期（不指定则自动取本地缓存中最新的有效交易日）',
    )
    p_monitor.add_argument(
        '--sector', metavar='板块名', default='沪深A股',
        help='股票池板块（默认 沪深A股），用于全景扫描和涨停板监控的股票范围',
    )
    p_monitor.add_argument(
        '--classification', metavar='分类', default='SW1',
        choices=['SW1', 'SW2', 'SW3', 'CSRC1', 'CSRC2'],
        help='行业分类体系（默认 SW1 申万一级），可选 SW1/SW2/SW3/CSRC1/CSRC2',
    )
    p_monitor.add_argument(
        '--output', metavar='路径', default=None,
        help='HTML 报告输出路径（不指定则默认 dashboard/market_report_{date}.html）',
    )

    return parser


# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _setup_logging(verbose=args.verbose)

    # ── 顶层 --list：展示品类体系后退出 ────────────────────────
    if getattr(args, 'list', False):
        _sync_list_categories()
        return

    # ── 未指定子命令时显示帮助 ─────────────────────────────────
    if not getattr(args, 'command', None):
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
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
