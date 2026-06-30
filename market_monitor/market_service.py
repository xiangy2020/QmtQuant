"""
market_service.py — 市场行情监控分析服务统一入口（Layer 2）

遵循两层架构规范：
  CLI → MarketMonitorService (本文件) → Layer 1 (market_overview / limit_up_monitor / sector_rotation / report_builder)

职责：
  - 接收 CLI 传入的 params，按 type 参数分发到各子模块
  - 通过 ServiceCallbacks 回调接口上报进度和日志
  - 单只股票失败不中断整体流程
  - 最终调用 report_builder 生成 HTML 报告
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_manager.data_service import ServiceCallbacks

logger = logging.getLogger(__name__)


class MarketMonitorService:
    """
    市场行情监控分析服务。

    统一入口，按 type 参数分发调用各子模块：
      - overview:  市场全景扫描
      - limit-up:  涨停板/个股异动监控
      - sector:    行业板块轮动分析
      - all:       全部（默认）

    使用示例：
        service = MarketMonitorService()
        result = service.run(
            params={
                'type': 'all',          # 分析类型
                'date': '20260522',     # 分析日期（不指定则自动取最新有效交易日）
                'sector': '沪深A股',    # 股票池板块
                'output': None,         # HTML 输出路径（不指定则默认 dashboard/）
            },
            callbacks=ServiceCallbacks(),
        )
        # result['success']:      bool
        # result['output_path']:  str  HTML 文件路径
        # result['trade_date']:   str  实际分析日期 YYYYMMDD
    """

    def run(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
    ) -> dict:
        """
        执行市场行情监控分析，生成 HTML 报告。

        Args:
        params: 分析参数字典，支持以下字段：
                type:           str  分析类型：'overview' | 'limit-up' | 'sector' | 'all'（默认 'all'）
                date:           str  分析日期 YYYYMMDD（不指定则自动取最新有效交易日）
                sector:         str  股票池板块（默认 '沪深A股'）
                classification: str  行业分类前缀（默认 'SW1'，可选 'SW2'/'CSRC1'/'CSRC2' 等）
                output:         str  HTML 输出路径（不指定则默认 dashboard/market_report_{date}.html）
            callbacks: ServiceCallbacks 实例，用于上报进度和日志

        Returns:
            dict:
                success:      bool   是否成功
                output_path:  str    HTML 文件路径（成功时）
                trade_date:   str    实际分析日期 YYYYMMDD
                message:      str    错误信息（失败时）
        """
        cb = callbacks or ServiceCallbacks()

        # ── 解析参数 ──────────────────────────────────────────────
        analysis_type  = params.get('type', 'all')
        date_str       = params.get('date')          # 可能为 None
        sector         = params.get('sector', '沪深A股')
        classification = params.get('classification', 'SW1')
        output_path    = params.get('output')

        cb.on_log(f"[MarketMonitor] 开始分析，类型={analysis_type}，板块={sector}，行业分类={classification}")

        try:
            # ── 延迟导入子模块（避免循环依赖）────────────────────
            from .data_loader import DataLoader
            from .market_overview import MarketOverview
            from .limit_up_monitor import LimitUpMonitor
            from .sector_rotation import SectorRotation
            from .report_builder import ReportBuilder

            # ── 初始化数据加载器，确定分析日期 ────────────────────
            loader = DataLoader(cb)
            trade_date = loader.resolve_trade_date(date_str)
            if trade_date is None:
                msg = f"无法确定分析日期：{'指定日期 ' + date_str + ' 无数据' if date_str else '本地缓存无有效数据'}"
                cb.on_error(msg)
                return {'success': False, 'message': msg, 'trade_date': date_str or ''}

            cb.on_log(f"[MarketMonitor] 分析日期：{trade_date}")

            # ── 按 type 分发执行各子模块 ──────────────────────────
            overview_data   = None
            limit_up_data   = None
            sector_data     = None

            run_overview  = analysis_type in ('overview', 'all')
            run_limit_up  = analysis_type in ('limit-up', 'all')
            run_sector    = analysis_type in ('sector', 'all')

            total_steps = sum([run_overview, run_limit_up, run_sector])
            done_steps  = 0

            if run_overview:
                cb.on_log("[MarketMonitor] 执行市场全景扫描...")
                overview = MarketOverview(loader)
                overview_data = overview.analyze(trade_date, sector)
                done_steps += 1
                cb.on_progress(done_steps, total_steps)

            if run_limit_up:
                cb.on_log("[MarketMonitor] 执行涨停板/个股异动监控...")
                monitor = LimitUpMonitor(loader)
                limit_up_data = monitor.analyze(trade_date, sector)
                done_steps += 1
                cb.on_progress(done_steps, total_steps)

            if run_sector:
                cb.on_log(f"[MarketMonitor] 执行行业板块轮动分析（{classification}）...")
                rotation = SectorRotation(loader)
                sector_data = rotation.analyze(trade_date, classification=classification)
                done_steps += 1
                cb.on_progress(done_steps, total_steps)

            # ── 生成 HTML 报告 ────────────────────────────────────
            cb.on_log("[MarketMonitor] 生成 HTML 报告...")
            builder = ReportBuilder()
            html_path = builder.build(
                trade_date=trade_date,
                overview_data=overview_data,
                limit_up_data=limit_up_data,
                sector_data=sector_data,
                output_path=output_path,
            )

            cb.on_log(f"[MarketMonitor] 报告已生成：{html_path}")
            result = {
                'success':     True,
                'output_path': html_path,
                'trade_date':  trade_date,
                'message':     '',
            }
            cb.on_done(result)
            return result

        except Exception as e:
            msg = f"[MarketMonitor] 分析失败：{e}"
            logger.exception(msg)
            cb.on_error(msg)
            return {
                'success':     False,
                'output_path': '',
                'trade_date':  date_str or '',
                'message':     str(e),
            }
