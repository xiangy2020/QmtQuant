"""
cmd_monitor.py — market monitor 子命令实现

CLI 入口：python dm_cli.py monitor [options]

支持参数：
  --type    分析类型：overview / limit-up / sector / all（默认 all）
  --date    分析日期 YYYYMMDD（不指定则自动取最新有效交易日）
  --sector  股票池板块（默认 沪深A股）
  --output  HTML 输出路径（不指定则默认 dashboard/market_report_{date}.html）
"""
from __future__ import annotations

import sys
from pathlib import Path

from dm_cli.common import _setup_logging, _err, _info


def cmd_monitor(args) -> None:
    """monitor 子命令入口"""
    _setup_logging(verbose=getattr(args, 'verbose', False))

    # ── 导入服务层 ────────────────────────────────────────────────
    try:
        from market_monitor import MarketMonitorService
        from data_manager.data_service import ServiceCallbacks
    except ImportError as e:
        _err(f"导入 market_monitor 模块失败：{e}")
        sys.exit(1)

    # ── 构建 params ────────────────────────────────────────────────
    params = {
        'type':           args.type,
        'date':           args.date,
        'sector':         args.sector,
        'classification': args.classification,
        'output':         args.output,
    }
    # ── 构建回调（将进度和日志输出到终端）────────────────────────
    class _CliCallbacks(ServiceCallbacks):
        def on_progress(self, done: int, total: int) -> None:
            pct = int(done / total * 100) if total else 0
            print(f"  进度：{done}/{total} ({pct}%)", flush=True)

        def on_log(self, message: str) -> None:
            print(f"  {message}", flush=True)

        def on_error(self, error: str) -> None:
            print(f"  ❌ {error}", file=sys.stderr, flush=True)

        def on_done(self, result: dict) -> None:
            pass

    # ── 执行分析 ──────────────────────────────────────────────────
    print(f"\n🚀 开始市场行情监控分析...")
    print(f"   类型：{args.type}  板块：{args.sector}  行业分类：{args.classification}  日期：{args.date or '自动'}\n")

    service = MarketMonitorService()
    result  = service.run(params=params, callbacks=_CliCallbacks())

    # ── 输出结果 ──────────────────────────────────────────────────
    if result.get('success'):
        output_path = result.get('output_path', '')
        trade_date  = result.get('trade_date', '')
        print(f"\n✅ 分析完成！数据日期：{trade_date}")
        print(f"\n📄 HTML 报告已生成：")
        print(f"   {output_path}")
        print(f"\n💡 用浏览器打开查看：")
        print(f"   open \"{output_path}\"")
    else:
        msg = result.get('message', '未知错误')
        _err(f"分析失败：{msg}")
        sys.exit(1)
