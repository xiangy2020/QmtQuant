# -*- coding: utf-8 -*-
"""
data_service.py — 数据管理服务层（Layer 2）

遵循两层架构规范：
  CLI → DataService (本文件) → Layer 1 (data_manager / utils)

职责：
  - 封装数据下载（全量/增量）
  - 封装缺失补充（从 Parquet 缓存检测缺口后补充）
  - 封装数据同步（miniQMT → Parquet）
  - 封装辅助数据同步（交易日历 / 合约信息）
  - 封装缓存管理（统计 / 校验 / 清理）

设计原则：
- 纯 Python，独立可运行
  - 所有长耗时方法通过 callbacks 传递进度和日志
  - 支持 stop_flag 中断
  - 可在独立进程（multiprocessing.Process）中安全调用
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# 统一回调接口
# ──────────────────────────────────────────────────────────────────

class ServiceCallbacks:
    """
    后端服务统一回调接口。

外部调用方通过继承或组合此类，将回调与适配器绑定。
    """

    def on_progress(self, done: int, total: int) -> None:
        """进度回调：done=已完成数量，total=总数量"""
        pass

    def on_log(self, message: str) -> None:
        """日志回调"""
        pass

    def on_error(self, error: str) -> None:
        """错误回调"""
        pass

    def on_done(self, result: dict) -> None:
        """完成回调"""
        pass


class ServiceCallbacksAdapter(ServiceCallbacks):
    """
将外部回调适配为 ServiceCallbacks 接口。

在子线程中使用：

        callbacks = ServiceCallbacksAdapter(
            progress_signal=self.progress,
            log_signal=self.status_update,
            error_signal=self.error,
            done_signal=self.finished,
        )
        DataService().download(params, callbacks)
    """

    def __init__(
        self,
        progress_signal=None,
        log_signal=None,
        error_signal=None,
        done_signal=None,
    ):
        self._progress = progress_signal
        self._log = log_signal
        self._error = error_signal
        self._done = done_signal

    def on_progress(self, done: int, total: int) -> None:
        if self._progress is not None:
            pct = int(done / total * 100) if total > 0 else 0
            try:
                self._progress.emit(pct)
            except Exception:
                pass

    def on_log(self, message: str) -> None:
        if self._log is not None:
            try:
                self._log.emit(str(message))
            except Exception:
                pass

    def on_error(self, error: str) -> None:
        if self._error is not None:
            try:
                self._error.emit(str(error))
            except Exception:
                pass

    def on_done(self, result: dict) -> None:
        if self._done is not None:
            try:
                self._done.emit(result)
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────
# DataService
# ──────────────────────────────────────────────────────────────────

class DataService:
    """
    数据管理服务层。

所有方法均为纯 Python，可在子进程中安全调用。

    使用示例（在子线程中）：
        service = DataService()
        callbacks = ServiceCallbacksAdapter(
            progress_signal=self.progress,
            log_signal=self.status_update,
        )
        result = service.download(params, callbacks, stop_flag=lambda: self._stop)
    """

    # ------------------------------------------------------------------
    # 数据下载（全量 / 增量 / 缺口）
    # ------------------------------------------------------------------

    def download(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        数据下载服务，支持三种模式：

          - full（全量）：强制重新下载指定日期范围内的全部数据
          - incremental（增量）：从 miniQMT 本地最后一条数据往后补充
          - gap（缺口）：扫描 Parquet 缓存缺口，逐段精准补充

        params 字段：
            stock_list:   list[str]  股票代码列表（必填）
            period_type:  str        数据周期，如 '1d'（必填）
            mode:         str        补充模式：'full' | 'incremental' | 'gap'
                                     默认 'incremental'
            asset_type:   str        一级品类，默认 'stock'（预留扩展）
            sub_type:     str        二级子类，默认 'kline'（预留扩展）

            # full / incremental 模式专用：
            start_date:   str        起始日期 YYYYMMDD（full 模式必填；incremental 模式留空）
            end_date:     str        结束日期 YYYYMMDD（可选，默认今天）

        Returns:
            full / incremental 模式：
                {'success': bool, 'message': str, 'mode': str}
            gap 模式：
                {
                    'success': bool, 'message': str, 'mode': str,
                    'interrupted': bool,
                    'processed': int,   # 有缓存且参与缺口计算的股票数
                    'has_gap': int,     # 有缺口的股票数
                    'no_gap': int,      # 无缺口的股票数
                    'no_cache': int,    # 无缓存跳过的股票数
                    'total_segments': int,
                    'done_segments': int,
                }
        """
        mode = params.get('mode', 'incremental')
        if mode == 'gap':
            return self._download_gap(params, callbacks, stop_flag)
        else:
            return self._download_impl(params, callbacks, stop_flag)

    # ── 时间段分批辅助方法 ────────────────────────────────────────
    @staticmethod
    def _split_time_segments(start_date: str, end_date: str, years_per_seg: int) -> list:
        """
        将 [start_date, end_date] 按年数切分为多个时间段。

        Args:
            start_date:    起始日期，格式 'YYYYMMDD'
            end_date:      结束日期，格式 'YYYYMMDD'（空字符串表示今天）
            years_per_seg: 每段年数

        Returns:
            [(seg_start, seg_end), ...]，格式均为 'YYYYMMDD'
        """
        from datetime import date, timedelta

        def parse_date(s: str) -> date:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))

        def fmt_date(d: date) -> str:
            return d.strftime('%Y%m%d')

        today = date.today()
        d_start = parse_date(start_date)
        d_end = parse_date(end_date) if end_date else today

        segments = []
        seg_start = d_start
        while seg_start <= d_end:
            # 每段结束日 = 起始年 + years_per_seg 年的 12月31日
            seg_end_year = seg_start.year + years_per_seg - 1
            seg_end = date(seg_end_year, 12, 31)
            seg_end = min(seg_end, d_end)
            segments.append((fmt_date(seg_start), fmt_date(seg_end)))
            # 下一段从下一年1月1日开始
            seg_start = date(seg_end_year + 1, 1, 1)

        return segments

    @staticmethod
    def _need_time_split(period_type: str, start_date: str) -> tuple:
        """
        判断是否需要按时间段分批，返回 (need_split, years_per_seg)。

        只有全量模式（start_date 有值）且为分钟级周期时才分批。
        增量模式（start_date 为空）不分批，因为只补最近缺口，数据量小。

        分段策略：
          1m         → 每段 1 年（数据量最大）
          5m/15m/30m → 每段 2 年
          其他周期   → 不分段
        """
        if not start_date:
            return False, 0
        minute_periods_1y = {'1m'}
        minute_periods_2y = {'5m', '15m', '30m'}
        if period_type in minute_periods_1y:
            return True, 1
        if period_type in minute_periods_2y:
            return True, 2
        return False, 0

    def _download_impl(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        全量 / 增量补充内部实现。

        必须使用 client.download_history_data2()（服务端封装版），
        而不是 xtdata.download_history_data2()（RPyC 透传版）。

        原因：miniQMT 的 download_history_data2 本身是异步接口，调用后立即返回，
        数据在后台异步传输。RPyC 透传版无法感知下载完成，会导致批次连续发出、
        数据实际未下载完成就进入下一批。

        服务端封装版在 Windows 本地用 threading.Event 等待 callback 触发
        finished >= total 后才返回，是真正的同步阻塞调用。

        时间段分批：
        对于分钟级周期（1m/5m/15m/30m）的全量下载，单次 RPC 调用可能超过
        RPyC 默认 300 秒超时。此时自动按年度切分时间段，逐段调用，
        每段数据量可控，不会触发超时。增量模式不分段（只补最近缺口）。
        """
        cb = callbacks or ServiceCallbacks()
        mode = params.get('mode', 'incremental')
        mode_label = '全量' if mode == 'full' else '增量'

        try:
            import xqshare as _xqshare

            stock_list = params['stock_list']
            period_type = params['period_type']
            start_date = params.get('start_date', '')
            end_date = params.get('end_date', '')
            incrementally = (mode != 'full')
            batch_size = params.get('batch_size') or 0  # 0 表示不分批（按股票数量）

            total = len(stock_list)
            cb.on_log(f'开始{mode_label}补充，共 {total} 只股票，周期 {period_type}')

            if stop_flag and stop_flag():
                result = {'success': False, 'message': f'{mode_label}补充已被用户中断', 'mode': mode}
                cb.on_done(result)
                return result

            client = _xqshare.get_client()
            if client is None:
                raise RuntimeError("xqshare 未连接，请先调用 connect()")

            # ── 判断是否需要按时间段分批 ──────────────────────────
            need_time_split, years_per_seg = self._need_time_split(period_type, start_date)
            if need_time_split:
                time_segments = self._split_time_segments(start_date, end_date, years_per_seg)
            else:
                time_segments = None

            # ── 内部下载函数（单次调用，支持股票数量分批） ──────────
            def _do_download(s_list: list, seg_start: str, seg_end: str):
                """对 s_list 按 batch_size 分批，在 [seg_start, seg_end] 范围内下载。"""
                if batch_size > 0 and len(s_list) > batch_size:
                    batches = [s_list[i:i + batch_size] for i in range(0, len(s_list), batch_size)]
                    for b_idx, batch in enumerate(batches, 1):
                        if stop_flag and stop_flag():
                            raise InterruptedError()
                        client.download_history_data2(
                            stock_list=batch,
                            period=period_type,
                            start_time=seg_start,
                            end_time=seg_end,
                            incrementally=incrementally,
                        )
                else:
                    client.download_history_data2(
                        stock_list=s_list,
                        period=period_type,
                        start_time=seg_start,
                        end_time=seg_end,
                        incrementally=incrementally,
                    )

            # ── 按时间段分批下载 ──────────────────────────────────
            if time_segments:
                total_segs = len(time_segments)
                cb.on_log(f'分钟级数据按时间段分批：共 {total_segs} 段，每段 {years_per_seg} 年')
                for seg_idx, (seg_start, seg_end) in enumerate(time_segments, 1):
                    if stop_flag and stop_flag():
                        result = {'success': False, 'message': f'{mode_label}补充已被用户中断', 'mode': mode}
                        cb.on_done(result)
                        return result
                    cb.on_progress(seg_idx - 1, total_segs)
                    cb.on_log(f'  ⏳ 第 {seg_idx}/{total_segs} 段：{seg_start} ~ {seg_end} 下载中...')
                    _do_download(stock_list, seg_start, seg_end)
                    cb.on_log(f'  ✓ 第 {seg_idx}/{total_segs} 段完成')
                    cb.on_progress(seg_idx, total_segs)

            # ── 按股票数量分批下载（原有逻辑） ────────────────────
            elif batch_size > 0 and total > batch_size:
                batches = [stock_list[i:i + batch_size] for i in range(0, total, batch_size)]
                total_batches = len(batches)
                cb.on_log(f'分批模式：共 {total_batches} 批，每批最多 {batch_size} 只')
                for idx, batch in enumerate(batches, 1):
                    if stop_flag and stop_flag():
                        result = {'success': False, 'message': f'{mode_label}补充已被用户中断', 'mode': mode}
                        cb.on_done(result)
                        return result
                    prev_done = min((idx - 1) * batch_size, total)
                    cb.on_progress(prev_done, total)
                    cb.on_log(f'  ⏳ 第 {idx}/{total_batches} 批：{len(batch)} 只（{batch[0]}{"..." if len(batch) > 1 else ""}）下载中...')
                    client.download_history_data2(
                        stock_list=batch,
                        period=period_type,
                        start_time=start_date,
                        end_time=end_date,
                        incrementally=incrementally,
                    )
                    done_count = min(idx * batch_size, total)
                    cb.on_log(f'  ✓ 第 {idx}/{total_batches} 批完成（{done_count}/{total}）')
                    cb.on_progress(done_count, total)

            # ── 不分批，直接下载 ──────────────────────────────────
            else:
                client.download_history_data2(
                    stock_list=stock_list,
                    period=period_type,
                    start_time=start_date,
                    end_time=end_date,
                    incrementally=incrementally,
                )

            cb.on_progress(total, total)
            result = {'success': True, 'message': f'{mode_label}补充完成！共 {total} 只股票', 'mode': mode}
            cb.on_log(result['message'])
            cb.on_done(result)
            return result

        except InterruptedError:
            result = {'success': False, 'message': f'{mode_label}补充已被用户中断', 'mode': mode}
            cb.on_log(f'⚠ {mode_label}补充已被用户中断')
            cb.on_done(result)
            return result
        except Exception as e:
            msg = f'{mode_label}补充出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            result = {'success': False, 'message': msg, 'mode': mode}
            cb.on_done(result)
            return result

    def _download_gap(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        缺口补充内部实现。

        从 Parquet 缓存读取已有日期，与交易日历对比，
        计算缺口段，调用 xtdata.download_history_data2 逐段补充。
        """
        cb = callbacks or ServiceCallbacks()

        try:
            from env import xtdata
            from data_manager.data_integrity import (
                get_cached_dates,
                get_date_range,
                calc_gap_segments,
            )

            stock_list = params['stock_list']
            period_type = params['period_type']
            total = len(stock_list)

            # ── 1. 获取交易日历 ──────────────────────────────────
            cb.on_log('正在获取交易日历...')
            try:
                trading_dates_sorted = self._fetch_trading_dates_sorted()
            except Exception as e:
                cb.on_error(str(e))
                return {
                    'success': False, 'message': str(e), 'mode': 'gap',
                    'interrupted': False, 'processed': 0, 'has_gap': 0,
                    'no_gap': 0, 'no_cache': 0, 'total_segments': 0, 'done_segments': 0,
                }

            cb.on_log(f'交易日历加载完成，共 {len(trading_dates_sorted)} 个交易日')

            today_str = datetime.now().strftime('%Y-%m-%d')

            # ── 2. 遍历股票池，逐股计算缺口并补充 ───────────────
            cnt_processed = 0
            cnt_has_gap = 0
            cnt_no_gap = 0
            cnt_no_cache = 0
            total_segments = 0
            done_segments = 0

            for idx, symbol in enumerate(stock_list):
                if stop_flag and stop_flag():
                    break

                cb.on_progress(idx, total)

                # 从 Parquet 缓存读取已有日期（格式统一为 'YYYY-MM-DD'）
                actual_dates = get_cached_dates(symbol, period_type)
                range_start, _ = get_date_range(symbol, period_type)

                if not actual_dates or not range_start:
                    cb.on_log(f'[{symbol}] 无本地缓存，跳过缺口补充（请先执行数据同步）')
                    cnt_no_cache += 1
                    continue

                cnt_processed += 1

                # 计算缺口段（两边日期格式均为 'YYYY-MM-DD'，格式已统一）
                segments = calc_gap_segments(
                    actual_dates, trading_dates_sorted, range_start, today_str
                )

                if not segments:
                    cnt_no_gap += 1
                    continue

                cnt_has_gap += 1
                total_segments += len(segments)
                cb.on_log(f'[{symbol}] 发现 {len(segments)} 个缺口段，开始补充...')

                for seg_start, seg_end in segments:
                    if stop_flag and stop_flag():
                        break

                    cb.on_log(f'  → 补充 {symbol} {period_type} {seg_start}~{seg_end}')
                    try:
                        xtdata.download_history_data2(
                            [symbol],
                            period=period_type,
                            start_time=seg_start,
                            end_time=seg_end,
                            incrementally=True,
                        )
                        done_segments += 1
                        cb.on_log(f'  ✓ 完成 {symbol} {seg_start}~{seg_end}')
                    except Exception as e:
                        cb.on_log(f'  ✗ 补充失败 {symbol} {seg_start}~{seg_end}: {e}')

            cb.on_progress(total, total)

            # ── 3. 汇总 ──────────────────────────────────────────
            interrupted = bool(stop_flag and stop_flag())
            remaining = total_segments - done_segments

            summary_msg = (
                f"缺口补充{'已中断' if interrupted else '完成'}｜"
                f"处理股票：{cnt_processed}，"
                f"有缺口：{cnt_has_gap}，"
                f"无缺口跳过：{cnt_no_gap}，"
                f"无缓存跳过：{cnt_no_cache}，"
                f"总缺口段：{total_segments}，"
                f"成功补充：{done_segments}"
                + (f"，剩余未处理：{remaining}" if interrupted else "")
            )

            result = {
                'success': not interrupted,
                'message': summary_msg,
                'mode': 'gap',
                'interrupted': interrupted,
                'processed': cnt_processed,
                'has_gap': cnt_has_gap,
                'no_gap': cnt_no_gap,
                'no_cache': cnt_no_cache,
                'total_segments': total_segments,
                'done_segments': done_segments,
            }
            cb.on_log(summary_msg)
            cb.on_done(result)
            return result

        except Exception as e:
            msg = f'缺口补充出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            result = {
                'success': False, 'message': msg, 'mode': 'gap',
                'interrupted': False, 'processed': 0, 'has_gap': 0,
                'no_gap': 0, 'no_cache': 0, 'total_segments': 0, 'done_segments': 0,
            }
            cb.on_done(result)
            return result

    def gap_download(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        缺口下载服务（内部调用 download(mode='gap')）。

        params 字段：
            stock_list:   list[str]  股票代码列表
            period_type:  str        数据周期，如 '1d'
        """
        return self.download(
            {**params, 'mode': 'gap'},
            callbacks=callbacks,
            stop_flag=stop_flag,
        )

    # ------------------------------------------------------------------
    # 数据同步（miniQMT → Parquet）
    # ------------------------------------------------------------------

    def sync(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        数据同步服务（miniQMT → Parquet）。

        params 字段：
            symbols:      list[str]  股票代码列表
            periods:      list[str]  数据周期列表
            start_date:   str        起始日期 YYYYMMDD
            end_date:     str        结束日期 YYYYMMDD，'' 表示最新

        Returns:
            {'success': int, 'failed': int, 'skipped': int, 'elapsed': float}
        """
        cb = callbacks or ServiceCallbacks()

        try:
            from data_manager.sync_pipeline import SyncPipeline, MiniQMTSource, ParquetSink

            symbols = params['symbols']
            periods = params['periods']
            start_date = params.get('start_date', '19900101')
            end_date = params.get('end_date', '')
            batch_size = params.get('batch_size') or 0  # 0 表示不分批
            asset_type = params.get('asset_type', 'stock')
            total = len(symbols) * len(periods)

            pipeline = SyncPipeline(source=MiniQMTSource(), sink=ParquetSink(asset_type=asset_type))

            # 分批处理
            if batch_size > 0 and len(symbols) > batch_size:
                batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
                total_batches = len(batches)
                cb.on_log(f'分批模式：共 {total_batches} 批，每批最多 {batch_size} 只')
            else:
                batches = [symbols]
                total_batches = 1

            agg = {'success': 0, 'failed': 0, 'skipped': 0, 'elapsed': 0.0}
            done_symbols = 0

            for batch_idx, batch_symbols in enumerate(batches):
                if stop_flag and stop_flag():
                    break
                if total_batches > 1:
                    cb.on_log(f'第 {batch_idx + 1}/{total_batches} 批（{len(batch_symbols)} 只）...')

                _offset = done_symbols * len(periods)

                def _on_progress(done, t, _off=_offset):
                    cb.on_progress(_off + done, total)

                batch_result = pipeline.run(
                    symbols=batch_symbols,
                    periods=periods,
                    start_date=start_date,
                    end_date=end_date,
                    on_progress=_on_progress,
                    on_item=lambda sym, per, ok, msg: cb.on_log(
                        f"{'✓' if ok else '✗'} [{sym} {per}] {msg}"
                    ),
                    stop_flag=stop_flag,
                )
                agg['success'] += batch_result.get('success', 0)
                agg['failed']  += batch_result.get('failed', 0)
                agg['skipped'] += batch_result.get('skipped', 0)
                agg['elapsed'] += batch_result.get('elapsed', 0.0)
                done_symbols += len(batch_symbols)

            result = agg
            summary = (
                f"同步完成 | 成功：{result['success']} | "
                f"失败：{result['failed']} | 跳过：{result['skipped']} | "
                f"耗时：{result['elapsed']:.1f}s"
            )
            cb.on_log(summary)
            cb.on_done(result)
            return result

        except Exception as e:
            msg = f'数据同步出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            result = {'success': 0, 'failed': 0, 'skipped': 0, 'elapsed': 0.0, 'message': msg}
            cb.on_done(result)
            return result

    # ------------------------------------------------------------------
    # 辅助数据同步（交易日历 + 合约信息）
    # ------------------------------------------------------------------

    def sync_aux_data(
        self,
        symbol_list: Optional[List[str]] = None,
        callbacks: Optional[ServiceCallbacks] = None,
    ) -> dict:
        """
        同步辅助数据：交易日历 + 合约基础信息。

        Args:
            symbol_list: 需要同步合约信息的股票代码列表，None 时跳过合约信息同步
            callbacks:   回调接口

        Returns:
            {'calendar_ok': bool, 'detail_ok': bool, 'detail_count': int}
        """
        cb = callbacks or ServiceCallbacks()
        result = {'calendar_ok': False, 'detail_ok': False, 'detail_count': 0}

        try:
            from env import xtdata
            from data_manager.aux_data import (
                save_trading_calendar as _save_cal,
                save_instrument_detail as _save_detail,
            )

            if xtdata is None:
                cb.on_error('xtdata 未初始化，请检查 xqshare 连接')
                return result

            # ── 同步交易日历 ──────────────────────────────────────
            try:
                cb.on_log('  ▶ 同步交易日历...')
                import datetime as _dt
                from env import xtdata
                raw_cal = xtdata.get_trading_dates('SH', start_time='19900101', end_time='')
                dates: List[str] = []
                for d in (raw_cal or []):
                    try:
                        s = str(int(d))
                        if len(s) in (12, 13):
                            # 12/13位均为毫秒时间戳 → 北京本地时间，禁止用 utcfromtimestamp
                            dt = _dt.datetime.fromtimestamp(int(d) / 1000)
                            dates.append(dt.strftime('%Y-%m-%d'))
                        elif len(s) == 8:
                            # 8位 YYYYMMDD
                            dates.append(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
                    except Exception:
                        pass
                dates = sorted(set(dates))
                if dates:
                    _save_cal(dates)
                    cb.on_log(f'  ✓ 交易日历已同步，共 {len(dates)} 个交易日')
                    result['calendar_ok'] = True
                else:
                    cb.on_log('  ✗ 交易日历返回为空')
            except Exception as e:
                cb.on_log(f'  ✗ 交易日历同步失败：{e}')

            # ── 同步合约基础信息 ──────────────────────────────────
            if symbol_list:
                try:
                    cb.on_log('  ▶ 同步合约基础信息...')
                    detail_dict: dict = {}
                    total_sym = len(symbol_list)

                    for idx, sym in enumerate(symbol_list):
                        try:
                            info = xtdata.get_instrument_detail(sym)
                            if info:
                                detail_dict[sym] = {
                                    'name':              str(info.get('InstrumentName', '') or ''),
                                    'exchange_id':       str(info.get('ExchangeID', '') or ''),
                                    'open_date':         str(info.get('OpenDate', '') or ''),
                                    'expire_date':       info.get('ExpireDate', 0),
                                    'pre_close':         info.get('PreClose', 0.0),
                                    'up_stop_price':     info.get('UpStopPrice', 0.0),
                                    'down_stop_price':   info.get('DownStopPrice', 0.0),
                                    'float_volume':      info.get('FloatVolume', 0.0),
                                    'total_volume':      info.get('TotalVolume', 0.0),
                                    'instrument_status': info.get('InstrumentStatus', 0),
                                    'is_trading':        bool(info.get('IsTrading', False)),
                                    'product_type':      info.get('ProductType', -1),
                                }
                        except Exception as e:
                            cb.on_log(f'  ✗ [{sym}] 合约信息获取失败：{e}')

                        if (idx + 1) % 200 == 0 or (idx + 1) == total_sym:
                            cb.on_log(f'  … 合约信息进度：{idx + 1}/{total_sym}')
                            cb.on_progress(idx + 1, total_sym)

                    _save_detail(detail_dict)
                    cb.on_log(f'  ✓ 合约基础信息已同步，共 {len(detail_dict)} 只股票')
                    result['detail_ok'] = True
                    result['detail_count'] = len(detail_dict)
                except Exception as e:
                    cb.on_log(f'  ✗ 合约基础信息同步失败：{e}')

            cb.on_log('▶ 辅助数据同步完成')
            cb.on_done(result)
            return result

        except Exception as e:
            msg = f'辅助数据同步出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            cb.on_done(result)
            return result

    # ------------------------------------------------------------------
    # 行业概念数据同步（sector_list + members）
    # ------------------------------------------------------------------

    def sync_industry_data(
        self,
        params: Optional[dict] = None,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        同步行业概念数据：板块分类信息（sector_list）+ 成分股列表（members）。

        纯读取 miniQMT 本地缓存，不触发任何网络下载（与 sync 命令行为一致）。
        如需先更新 miniQMT 本地板块数据，请在外部手动调用 xtdata.download_sector_data()。

        执行顺序：
          1. 同步 sector_list（板块名称列表 → Parquet）
          2. 逐板块同步 members（成分股列表 → Parquet）

        params 字段：
            sectors: list[str]  可选，指定板块名称列表；不传则全量同步所有板块的成分股

        Returns:
            {
                'success': bool,
                'sector_list_ok': bool,
                'members_success': int,
                'members_failed': int,
                'total_sectors': int,
                'interrupted': bool,
            }
        """
        cb = callbacks or ServiceCallbacks()
        params = params or {}

        result = {
            'success': False,
            'sector_list_ok': False,
            'members_success': 0,
            'members_failed': 0,
            'total_sectors': 0,
            'interrupted': False,
        }

        try:
            from env import xtdata
            from data_manager.sync_pipeline import SyncPipeline, MiniQMTSource, ParquetSink

            if xtdata is None:
                msg = 'xtdata 未初始化，请检查 xqshare 连接'
                cb.on_error(msg)
                cb.on_done(result)
                return result

            pipeline = SyncPipeline(source=MiniQMTSource(), sink=ParquetSink())

            # ── 步骤1：同步 sector_list → Parquet ───────────────────
            cb.on_log('▶ 步骤1/2：同步板块列表（sector_list）...')
            sector_list_ok = pipeline.sync_sector_list()
            result['sector_list_ok'] = sector_list_ok
            if sector_list_ok:
                sectors_all = pipeline.source.get_sector_list()
                cb.on_log(f'  ✓ 板块列表已同步，共 {len(sectors_all)} 个板块')
            else:
                sectors_all = []
                cb.on_log('  ✗ 板块列表同步失败（数据源返回空）')

            if stop_flag and stop_flag():
                result['interrupted'] = True
                cb.on_log('⚠ 用户中断')
                cb.on_done(result)
                return result

            # ── 步骤3：逐板块同步 members ────────────────────────────
            # 若 params 中指定了 sectors，则只同步指定板块的成分股
            target_sectors = params.get('sectors')
            if target_sectors:
                sync_sectors = [s for s in target_sectors if s]
                cb.on_log(f'▶ 步骤2/2：同步指定板块成分股（{len(sync_sectors)} 个板块）...')
            else:
                sync_sectors = sectors_all
                cb.on_log(f'▶ 步骤2/2：同步全量板块成分股（{len(sync_sectors)} 个板块）...')

            total = len(sync_sectors)
            result['total_sectors'] = total
            members_success = 0
            members_failed = 0

            for idx, sector in enumerate(sync_sectors):
                if stop_flag and stop_flag():
                    result['interrupted'] = True
                    cb.on_log(f'⚠ 用户中断（已完成 {idx}/{total} 个板块）')
                    break

                cb.on_progress(idx, total)
                ok = pipeline.sync_sector_members(sector)
                if ok:
                    members_success += 1
                    cb.on_log(f'  ✓ [{idx + 1}/{total}] {sector}')
                else:
                    members_failed += 1
                    cb.on_log(f'  ✗ [{idx + 1}/{total}] {sector}（成分股为空或写入失败）')

            cb.on_progress(total, total)
            result['members_success'] = members_success
            result['members_failed'] = members_failed
            result['success'] = sector_list_ok and not result['interrupted']

            summary = (
                f"行业概念数据同步{'已中断' if result['interrupted'] else '完成'} | "
                f"板块总数：{total} | "
                f"成功：{members_success} | "
                f"失败：{members_failed}"
            )
            cb.on_log(summary)
            cb.on_done(result)
            return result

        except Exception as e:
            msg = f'行业概念数据同步出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            result['success'] = False
            cb.on_done(result)
            return result

    # ------------------------------------------------------------------
    # 指数基础信息同步
    # ------------------------------------------------------------------

    def sync_index_instrument(
        self,
        sector: str = '沪深指数',
        callbacks: Optional[ServiceCallbacks] = None,
    ) -> dict:
        """
        同步指数基础信息到 Parquet 缓存（index/instrument/instrument_detail.parquet）。

        执行流程：
          1. 调用 xtdata.get_stock_list_in_sector(sector) 获取指数代码列表
          2. 逐只调用 xtdata.get_instrument_detail() 获取基础信息（保存全部字段）
          3. 增量合并写入 ~/.qmtquant/cache/index/instrument/instrument_detail.parquet

        Args:
            sector:    板块名称，默认 '沪深指数'；也可指定 '上证指数'、'深证指数' 等
            callbacks: 回调接口，用于上报进度和日志

        Returns:
            {
                'success':      bool,  # 是否成功
                'count':        int,   # 成功写入的指数数量
                'message':      str,   # 结果描述
            }
        """
        cb = callbacks or ServiceCallbacks()
        from data_manager.download_handlers import IndexInstrumentDownloadHandler
        from data_manager.download_handlers import DownloadCallbacks

        class _Adapter(DownloadCallbacks):
            def on_progress(self, done, total):
                cb.on_progress(done, total)
            def on_log(self, message):
                cb.on_log(message)
            def on_error(self, error):
                cb.on_error(error)

        handler = IndexInstrumentdownloadHandler()
        result = handler.execute_batch(
            symbol_list=[],
            period='',
            start=None,
            end=None,
            mode='full',
            callbacks=_Adapter(),
            sector=sector,
        )
        cb.on_done(result)
        return result

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def get_cache_statistics(self) -> dict:
        """
        获取本地缓存整体统计信息。

        Returns:
            参见 data_manager.cache_manager.get_statistics()
        """
        try:
            from data_manager.cache_manager import get_statistics
            return get_statistics()
        except Exception as e:
            logger.error(f'get_cache_statistics 失败：{e}', exc_info=True)
            return {}

    def validate_cache(self, symbol: str, period: str) -> dict:
        """
        校验指定股票缓存文件的完整性。

        Returns:
            参见 data_manager.cache_manager.validate_cache()
        """
        try:
            from data_manager.cache_manager import validate_cache
            return validate_cache(symbol, period)
        except Exception as e:
            logger.error(f'validate_cache 失败：{e}', exc_info=True)
            return {'symbol': symbol, 'period': period, 'exists': False,
                    'readable': False, 'record_count': 0, 'error': str(e)}

    def clear_all_cache(self) -> dict:
        """
        清空所有本地 Parquet 缓存。

        Returns:
            参见 data_manager.cache_manager.clear_all()
        """
        try:
            from data_manager.cache_manager import clear_all
            return clear_all()
        except Exception as e:
            logger.error(f'clear_all_cache 失败：{e}', exc_info=True)
            return {'success': False, 'deleted_files': 0, 'freed_mb': 0.0, 'error': str(e)}

    def clear_symbol_cache(self, symbol: str, period: Optional[str] = None) -> dict:
        """
        清除指定股票的缓存（可指定周期）。

        Returns:
            参见 data_manager.cache_manager.clear_symbol()
        """
        try:
            from data_manager.cache_manager import clear_symbol
            return clear_symbol(symbol, period)
        except Exception as e:
            logger.error(f'clear_symbol_cache 失败：{e}', exc_info=True)
            return {'success': False, 'deleted_files': 0, 'freed_mb': 0.0, 'error': str(e)}

    def clear_date_anomaly(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        批量精准行级清理：删除股票缓存中早于 A 股开市日（1990-12-19）的脏数据行。

        仅删除异常行，保留正常数据，回写时保持原有 schema 不变。

        params 字段：
            stock_list: list[str]  股票代码列表（必填）
            period:     str        数据周期，如 '1d'（必填）

        Returns:
            {
                'success':            bool,  # 整体是否成功（未中断且无失败）
                'total':              int,   # 扫描总数
                'anomaly_found':      int,   # 发现异常的股票数
                'cleaned':            int,   # 成功清理的股票数
                'failed':             int,   # 清理失败的股票数
                'total_removed_rows': int,   # 共删除的异常行数
                'freed_mb':           float, # 共释放的磁盘空间（MB）
                'interrupted':        bool,
                'errors':             list,  # 失败详情 [{'symbol': str, 'error': str}, ...]
            }
        """
        cb = callbacks or ServiceCallbacks()

        empty_result = {
            'success': False, 'total': 0, 'anomaly_found': 0,
            'cleaned': 0, 'failed': 0, 'total_removed_rows': 0,
            'freed_mb': 0.0, 'interrupted': False, 'errors': [],
        }

        try:
            from data_manager.cache_manager import batch_clear_date_anomaly

            stock_list = params.get('stock_list', [])
            period = params.get('period', '')

            if not stock_list:
                cb.on_error('stock_list 不能为空')
                return empty_result
            if not period:
                cb.on_error('period 不能为空')
                return empty_result

            total = len(stock_list)
            cb.on_log(f'开始清理日期异常数据，共 {total} 只股票，周期 {period}')

            result = batch_clear_date_anomaly(
                symbol_list=stock_list,
                period=period,
                on_progress=lambda done, t: cb.on_progress(done, t),
                stop_flag=stop_flag,
            )

            cb.on_log(
                f"清理{'已中断' if result['interrupted'] else '完成'} | "
                f"扫描：{result['total']} | "
                f"发现异常：{result['anomaly_found']} | "
                f"成功清理：{result['cleaned']} | "
                f"失败：{result['failed']} | "
                f"共删除 {result['total_removed_rows']} 行"
            )
            return result

        except Exception as e:
            logger.error(f'clear_date_anomaly 失败：{e}', exc_info=True)
            empty_result['errors'].append({'symbol': '*', 'error': str(e)})
            return empty_result

    def clear_no_open_date(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        批量整个文件删除：删除上市日期缺失标的的 Parquet 缓存文件。

        内部先执行 validate 扫描找出 no_open_date == True 的标的，
        再调用 batch_delete_no_open_date 执行整个文件删除（非行级清理）。

        params 字段：
            stock_list:  list[str]       股票代码列表（必填）
            period:      str | None      数据周期，如 '1d'；None 表示删除所有周期（可选）
            sub_type_config: SubTypeConfig  子类配置实例（validate 所需，必填）

        Returns:
            {
                'success':   bool,   # 整体是否成功（未中断且无失败）
                'total':     int,    # 扫描总数
                'found':     int,    # 发现上市日期缺失的股票数
                'deleted':   int,    # 成功删除的股票数
                'failed':    int,    # 删除失败的股票数
                'freed_mb':  float,  # 共释放的磁盘空间（MB）
                'interrupted': bool,
                'errors':    list,   # 失败详情 [{'symbol': str, 'error': str}, ...]
            }
        """
        cb = callbacks or ServiceCallbacks()

        empty_result = {
            'success': False, 'total': 0, 'found': 0,
            'deleted': 0, 'failed': 0, 'freed_mb': 0.0,
            'interrupted': False, 'errors': [],
        }

        try:
            from pathlib import Path as _Path
            from data_manager.data_integrity import batch_validate
            from data_manager.cache_manager import batch_delete_no_open_date
            import pandas as pd

            stock_list = params.get('stock_list', [])
            period = params.get('period', None)
            sub_type_config = params.get('sub_type_config')

            if not stock_list:
                cb.on_error('stock_list 不能为空')
                return empty_result
            if sub_type_config is None:
                cb.on_error('sub_type_config 不能为空')
                return empty_result

            total = len(stock_list)
            empty_result['total'] = total

            # ── 1. 加载交易日历和合约信息（validate 所需）────────
            cache_root = _Path.home() / '.qmtquant' / 'cache'
            instrument_path = cache_root / 'stock' / 'instrument' / 'instrument_detail.parquet'

            if not instrument_path.exists():
                cb.on_error('合约信息缺失，请先执行 sync --asset stock --sub instrument')
                return empty_result

            cb.on_log('正在加载交易日历...')
            try:
                trading_dates_sorted = self._fetch_trading_dates_sorted()
            except Exception as e:
                cb.on_error(str(e))
                return empty_result

            cb.on_log('正在加载合约信息...')
            try:
                instrument_df = pd.read_parquet(instrument_path, engine='pyarrow')
            except Exception as e:
                cb.on_error(f'合约信息读取失败：{e}')
                return empty_result

            # ── 2. 执行 validate 扫描，找出 no_open_date 标的 ────
            cb.on_log(f'正在扫描上市日期缺失标的，共 {total} 只...')
            validate_results = batch_validate(
                symbol_list=stock_list,
                period=period or '1d',
                sub_type_config=sub_type_config,
                trading_dates_sorted=trading_dates_sorted,
                instrument_df=instrument_df,
                on_progress=lambda done, t: cb.on_progress(done, t),
                stop_flag=stop_flag,
            )

            no_open_date_symbols = [
                r['symbol'] for r in validate_results
                if r.get('no_open_date', False) and r.get('has_cache', False)
            ]
            found = len(no_open_date_symbols)
            cb.on_log(f'扫描完成，发现 {found} 只上市日期缺失的标的')

            if found == 0:
                empty_result['success'] = True
                empty_result['total'] = total
                return empty_result

            # ── 3. 批量删除整个缓存文件 ──────────────────────────
            cb.on_log(f'开始删除 {found} 只标的的缓存文件...')
            del_result = batch_delete_no_open_date(
                symbol_list=no_open_date_symbols,
                period=period,
                on_progress=lambda done, t: cb.on_progress(done, t),
                stop_flag=stop_flag,
            )

            cb.on_log(
                f"删除{'已中断' if del_result['interrupted'] else '完成'} | "
                f"发现：{found} | "
                f"成功删除：{del_result['deleted']} | "
                f"失败：{del_result['failed']} | "
                f"释放：{del_result['freed_mb']:.4f} MB"
            )

            return {
                'success':     del_result['success'],
                'total':       total,
                'found':       found,
                'deleted':     del_result['deleted'],
                'failed':      del_result['failed'],
                'freed_mb':    del_result['freed_mb'],
                'interrupted': del_result['interrupted'],
                'errors':      del_result['errors'],
            }

        except Exception as e:
            logger.error(f'clear_no_open_date 失败：{e}', exc_info=True)
            empty_result['errors'].append({'symbol': '*', 'error': str(e)})
            return empty_result

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def query_kline(
        self,
        symbol: str,
        period: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """
        从本地 Parquet 缓存查询 K 线数据（同步方法）。

        Args:
            symbol:     股票代码，如 '600000.SH'
            period:     数据周期，如 '1d'
            start_date: 起始日期，格式 'YYYYMMDD' 或 'YYYY-MM-DD'，None 表示不限
            end_date:   结束日期，格式同上，None 表示不限

        Returns:
            pd.DataFrame，若无数据则返回空 DataFrame
        """
        try:
            from data_manager.storage import get_default_storage
            storage = get_default_storage()
            return storage.load(symbol, period, start_date, end_date)
        except Exception as e:
            logger.error(f'query_kline 失败 [{symbol} {period}]：{e}', exc_info=True)
            import pandas as pd
            return pd.DataFrame()

    def get_sector(self, sector_name: str, sectors_cache_dir: Optional[str] = None) -> list:
        """
        从本地 Parquet 缓存读取板块成分股。

        读取路径：~/.qmtquant/cache/industry/members/{sector_name}.parquet
        （由 sync-industry 命令写入，格式：symbol, sector_name, updated_at）

        Args:
            sector_name:       板块名称
            sectors_cache_dir: 自定义板块缓存目录，None 时使用默认路径

        Returns:
            [[code, name], ...] 格式的列表
        """
        try:
            import pandas as pd
            safe_name = sector_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
            if sectors_cache_dir:
                sector_file = Path(sectors_cache_dir) / f"{safe_name}.parquet"
            else:
                sector_file = Path.home() / ".qmtquant" / "cache" / "industry" / "members" / f"{safe_name}.parquet"

            if not sector_file.exists():
                return []
            df = pd.read_parquet(sector_file, engine="pyarrow")
            if df.empty:
                return []
            # industry/members 格式：symbol, sector_name, updated_at
            if 'symbol' in df.columns:
                sector_col = df['sector_name'].tolist() if 'sector_name' in df.columns else [''] * len(df)
                return list(zip(df['symbol'].tolist(), sector_col))
            # 兜底：取前两列
            elif len(df.columns) >= 2:
                return df.iloc[:, :2].values.tolist()
            else:
                return [[row[0], ''] for row in df.values.tolist()]
        except Exception as e:
            logger.error(f'get_sector 失败 [{sector_name}]：{e}', exc_info=True)
            return []

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _fetch_trading_dates_sorted(self) -> List[str]:
        """
        获取完整交易日历（已排序列表，格式 'YYYY-MM-DD'）。

        从本地 Parquet 缓存读取（~/.qmtquant/cache/stock/calendar/trading_calendar.parquet）。
        缓存不存在时抛出 RuntimeError，由调用方决定如何处理。

        Returns:
            已排序的交易日列表（'YYYY-MM-DD' 格式）

        Raises:
            RuntimeError: 本地交易日历缓存缺失
        """
        from .aux_data import load_trading_calendar

        result = load_trading_calendar()
        if not result:
            raise RuntimeError(
                '交易日历缺失，请先执行 sync --asset stock --sub calendar'
            )
        logger.info(f'交易日历加载完成，共 {len(result)} 个交易日（本地缓存）')
        return result

    # ------------------------------------------------------------------
    # 全面数据健康检查（validate）
    # ------------------------------------------------------------------

    def validate_kline(
        self,
        params: dict,
        callbacks: Optional[ServiceCallbacks] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        对股票池执行全面数据健康检查（stock/kline）。

        执行顺序：
          1. 依赖链检查：calendar + instrument 文件是否存在
          2. 加载交易日历和合约信息
          3. 调用 batch_validate 批量校验
          4. 汇总结果

        params 字段：
            stock_list:   list[str]  股票代码列表（必填）
            period:       str        数据周期，如 '1d'（必填）
            sub_type_config: SubTypeConfig 实例（必填）

        Returns:
            {
                'success':        bool,
                'total':          int,   # 总扫描数
                'no_cache':       int,   # 无缓存数
                'field_error':    int,   # 字段不完整数
                'type_error':     int,   # 类型异常数
                'head_missing':   int,   # 前缺失数
                'tail_missing':   int,   # 后缺失数
                'gap':            int,   # 中间缺口数
                'date_anomaly':   int,   # 日期异常数（早于 A 股开市日 1990-12-19 的脏数据）
                'no_open_date':   int,   # 上市日期缺失数（合约信息中 open_date 为 None）
                'healthy':        int,   # 完全健康数
                'interrupted':    bool,
                'results':        list,  # 每只股票的 validate_symbol 结果
                # results 列表中每个字典的字段：
                #   symbol, has_cache, field_ok, type_ok,
                #   missing_fields, type_errors,
                #   head_missing, tail_missing,
                #   cache_start, cache_end, open_date,
                #   gap_segments, head_gap_segments, tail_start,
                #   date_anomaly, anomaly_count, anomaly_min_date,
                #   no_open_date,
                #   _debug: {
                #     open_date_raw, expire_date_raw,
                #     calendar_start, latest_trading,
                #     t1, t2,
                #     gap_segment_counts: list[int]  # 与 gap_segments 一一对应，每段缺口的交易日数
                #   }
            }
        """
        cb = callbacks or ServiceCallbacks()

        empty_result = {
            'success': False, 'total': 0, 'no_cache': 0,
            'field_error': 0, 'type_error': 0,
            'head_missing': 0, 'tail_missing': 0,
            'healthy': 0, 'interrupted': False, 'results': [],
        }

        try:
            import pandas as pd
            from pathlib import Path as _Path
            from data_manager.data_integrity import batch_validate

            stock_list = params['stock_list']
            period = params['period']
            sub_type_config = params['sub_type_config']
            asset_type = params.get('asset_type', 'stock')

            # ── 1. 依赖链检查 ─────────────────────────────────────
            cache_root = _Path.home() / '.qmtquant' / 'cache'
            calendar_path = cache_root / 'stock' / 'calendar' / 'trading_calendar.parquet'

            if not calendar_path.exists():
                msg = '交易日历缺失，请先执行 sync --asset stock --sub calendar'
                cb.on_error(msg)
                empty_result['success'] = False
                return empty_result

            # 指数品类：跳过 instrument 依赖检查（指数无上市日期，不做前缺失检测）
            if asset_type != 'index':
                instrument_path = cache_root / 'stock' / 'instrument' / 'instrument_detail.parquet'
                if not instrument_path.exists():
                    msg = '合约信息缺失，请先执行 sync --asset stock --sub instrument'
                    cb.on_error(msg)
                    empty_result['success'] = False
                    return empty_result

            # ── 2. 加载交易日历 ───────────────────────────────────
            cb.on_log('正在加载交易日历...')
            try:
                trading_dates_sorted = self._fetch_trading_dates_sorted()
            except Exception as e:
                cb.on_error(str(e))
                empty_result['success'] = False
                return empty_result
            cb.on_log(f'交易日历加载完成，共 {len(trading_dates_sorted)} 个交易日')

            # ── 3. 加载合约信息 ───────────────────────────────────
            # 指数品类：传 instrument_df=None，validate_symbol 会跳过前缺失检测
            if asset_type == 'index':
                instrument_df = None
                cb.on_log('品类为 index，跳过前缺失检测（指数无上市日期）')
            else:
                cb.on_log('正在加载合约信息...')
                try:
                    instrument_df = pd.read_parquet(instrument_path, engine='pyarrow')
                except Exception as e:
                    msg = f'合约信息读取失败：{e}'
                    cb.on_error(msg)
                    empty_result['success'] = False
                    return empty_result
                cb.on_log(f'合约信息加载完成，共 {len(instrument_df)} 条记录')

            # ── 4. 批量校验 ───────────────────────────────────────
            total = len(stock_list)
            cb.on_log(f'开始校验，共 {total} 只股票，周期 {period}')

            results = batch_validate(
                symbol_list=stock_list,
                period=period,
                sub_type_config=sub_type_config,
                trading_dates_sorted=trading_dates_sorted,
                instrument_df=instrument_df,
                on_progress=lambda done, t: cb.on_progress(done, t),
                stop_flag=stop_flag,
            )

            # ── 5. 汇总统计 ───────────────────────────────────────
            interrupted = bool(stop_flag and stop_flag())
            cnt_no_cache = sum(1 for r in results if not r['has_cache'])
            cnt_field_error = sum(1 for r in results if r['has_cache'] and not r['field_ok'])
            cnt_type_error = sum(1 for r in results if r['has_cache'] and not r['type_ok'])
            cnt_head_missing = sum(1 for r in results if r['head_missing'] > 0)
            cnt_tail_missing = sum(1 for r in results if r['tail_missing'] > 0)
            cnt_gap = sum(1 for r in results if r['has_cache'] and len(r.get('gap_segments', [])) > 0)
            cnt_date_anomaly = sum(1 for r in results if r.get('date_anomaly', False))
            cnt_no_open_date = sum(1 for r in results if r.get('no_open_date', False))
            cnt_healthy = sum(
                1 for r in results
                if r['has_cache']
                and r['field_ok']
                and r['type_ok']
                and r['head_missing'] == 0
                and r['tail_missing'] == 0
                and len(r.get('gap_segments', [])) == 0
                and not r.get('date_anomaly', False)
                and not r.get('no_open_date', False)  # 上市日期缺失不计入健康
            )

            summary = {
                'success':        not interrupted,
                'total':          len(results),
                'no_cache':       cnt_no_cache,
                'field_error':    cnt_field_error,
                'type_error':     cnt_type_error,
                'head_missing':   cnt_head_missing,
                'tail_missing':   cnt_tail_missing,
                'gap':            cnt_gap,
                'date_anomaly':   cnt_date_anomaly,
                'no_open_date':   cnt_no_open_date,
                'healthy':        cnt_healthy,
                'interrupted':    interrupted,
                'results':        results,
            }

            cb.on_log(
                f"校验{'已中断' if interrupted else '完成'} | "
                f"总计：{len(results)} | 健康：{cnt_healthy} | "
                f"无缓存：{cnt_no_cache} | 字段不完整：{cnt_field_error} | "
                f"类型异常：{cnt_type_error} | 前缺失：{cnt_head_missing} | "
                f"后缺失：{cnt_tail_missing} | 中间缺口：{cnt_gap}"
            )
            cb.on_done(summary)
            return summary

        except Exception as e:
            msg = f'validate_kline 出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            empty_result['success'] = False
            cb.on_done(empty_result)
            return empty_result

    # ── 智能下载（smart download）────────────────────────────────

    def smart_download(
        self,
        validate_result: dict,
        params: dict,
        callbacks=None,
        stop_flag: callable = None,
    ) -> dict:
        """
        基于 validate 结果执行通用精准数据修复（smart download）。

        直接消费 validate_kline 的扫描结果，按问题类型分层选择下载策略，
        避免重复扫描。支持任意品类，通过 SubTypeConfig.download_handler 路由。

        Args:
            validate_result: validate_kline 的返回字典（含 'results' 列表）
            params: 参数字典，包含：
                asset_type:    str  一级品类，如 'stock'
                sub_type:      str  二级子类，如 'kline'
                period:        str  数据周期，如 '1d'
                default_start: str  全量下载时无 open_date 的标的使用此起始日期（YYYYMMDD，可选）
            callbacks: ServiceCallbacks 实例（含 on_progress / on_log / on_error / on_done）
            stop_flag: 停止检查函数，返回 True 时在当前批次完成后停止

        Returns:
            {
                'success':        bool,
                'total_batches':  int,
                'done_batches':   int,
                'failed_batches': int,
                'download_count': int,   # 下载标的数（去重）
                'skipped_count':  int,   # 跳过标的数
                'interrupted':    bool,
                'layer_a_count':  int,
                'layer_b_count':  int,
                'layer_c_count':  int,
            }
        """
        from data_manager.asset_types import get_asset_type
        from data_manager.download_handlers import (
            build_download_plan,
            get_handler,
            DownloadCallbacks,
        )

        cb = callbacks or type('_CB', (), {
            'on_progress': lambda s, d, t: None,
            'on_log':      lambda s, m: None,
            'on_error':    lambda s, e: None,
            'on_done':     lambda s, r: None,
        })()

        empty_result = {
            'success':        False,
            'total_batches':  0,
            'done_batches':   0,
            'failed_batches': 0,
            'download_count': 0,
            'skipped_count':  0,
            'interrupted':    False,
            'layer_a_count':  0,
            'layer_b_count':  0,
            'layer_c_count':  0,
        }

        try:
            asset_type  = params.get('asset_type', 'stock')
            sub_type    = params.get('sub_type', 'kline')
            period      = params.get('period', '1d')
            default_start = params.get('default_start')

            # ── 1. 查找 SubTypeConfig ────────────────────────────
            at_config = get_asset_type(asset_type)
            if at_config is None:
                msg = f"smart_download：未知品类 {asset_type!r}"
                cb.on_error(msg)
                return empty_result

            sub_config = at_config.get_sub_type(sub_type)
            if sub_config is None:
                msg = f"smart_download：未知子类 {asset_type}/{sub_type}"
                cb.on_error(msg)
                return empty_result

            # ── 2. 检查处理器是否已注册 ──────────────────────────
            handler_id = getattr(sub_config, 'download_handler', None)
            if not handler_id:
                msg = f"smart_download：{asset_type}/{sub_type} 未配置 download_handler，跳过"
                cb.on_log(msg)
                return empty_result

            handler = get_handler(handler_id)
            if handler is None:
                msg = f"smart_download：处理器 '{handler_id}' 未注册，该子类暂不支持 smart 下载"
                cb.on_log(msg)
                return empty_result

            strategy = getattr(sub_config, 'download_strategy', [])
            if not strategy:
                msg = f"smart_download：{asset_type}/{sub_type} download_strategy 为空，跳过"
                cb.on_log(msg)
                return empty_result

            # ── 3. 生成下载计划 ──────────────────────────────────
            results_list = validate_result.get('results', [])
            if not results_list:
                cb.on_log("smart_download：validate 结果为空，无需下载")
                empty_result['success'] = True
                return empty_result

            plan = build_download_plan(
                validate_results=results_list,
                period=period,
                sub_type_config=sub_config,
                default_start=default_start,
            )

            cb.on_log(plan.summary())

            if plan.total_batches == 0:
                cb.on_log("✅ 数据健康，无需下载")
                empty_result['success'] = True
                return empty_result

            # ── 4. 适配回调接口 ──────────────────────────────────
            class _CallbackAdapter(downloadCallbacks):
                def __init__(self, outer_cb):
                    self._cb = outer_cb
                def on_log(self, message):
                    self._cb.on_log(message)
                def on_error(self, error):
                    self._cb.on_error(error)
                def on_progress(self, done, total):
                    self._cb.on_progress(done, total)

            handler_cb = _CallbackAdapter(cb)

            # ── 5. 按 Layer A → B → C 顺序执行 ──────────────────
            total_batches  = plan.total_batches
            done_batches   = 0
            failed_batches = 0
            interrupted    = False
            download_symbols: set = set()

            all_tasks = (
                [('A', t) for t in plan.layer_a] +
                [('B', t) for t in plan.layer_b] +
                [('C', t) for t in plan.layer_c]
            )

            layer_labels = {'A': 'Layer A（全量）', 'B': 'Layer B（缺口）', 'C': 'Layer C（增量）'}
            current_layer = None

            for layer, task in all_tasks:
                # 检查停止标志（在批次开始前检查）
                if stop_flag and stop_flag():
                    interrupted = True
                    cb.on_log("⚠ 收到停止信号，已中断")
                    break

                if layer != current_layer:
                    current_layer = layer
                    cb.on_log(f"\n▶ 开始执行 {layer_labels[layer]}")

                cb.on_log(f"  批次 {done_batches + 1}/{total_batches}：{task.desc}")

                batch_result = handler.execute_batch(
                    symbol_list=task.symbol_list,
                    period=task.period,
                    start=task.start,
                    end=task.end,
                    mode=task.mode,
                    callbacks=handler_cb,
                )

                done_batches += 1
                if batch_result.get('success'):
                    download_symbols.update(task.symbol_list)
                else:
                    failed_batches += 1
                    cb.on_log(f"  ⚠ 批次失败：{batch_result.get('message', '未知错误')}")

                cb.on_progress(done_batches, total_batches)

            # ── 6. 汇总结果 ──────────────────────────────────────
            summary = {
                'success':        not interrupted and failed_batches == 0,
                'total_batches':  total_batches,
                'done_batches':   done_batches,
                'failed_batches': failed_batches,
                'download_count': len(download_symbols),
                'skipped_count':  validate_result.get('total', 0) - len(download_symbols),
                'interrupted':    interrupted,
                'layer_a_count':  len(plan.layer_a_symbols),
                'layer_b_count':  len(plan.layer_b_symbols),
                'layer_c_count':  len(plan.layer_c_symbols),
            }

            cb.on_log(
                f"\nsmart_download {'已中断' if interrupted else '完成'} | "
                f"总批次：{total_batches} | 成功：{done_batches - failed_batches} | "
                f"失败：{failed_batches} | 下载标的：{len(download_symbols)}"
            )
            cb.on_done(summary)
            return summary

        except Exception as e:
            msg = f'smart_download 出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            cb.on_done(empty_result)
            return empty_result

    # ------------------------------------------------------------------
    # 智能同步（smart sync）：基于 validate 结果的精准增量同步
    # ------------------------------------------------------------------

    def sync_smart(
        self,
        validate_result: dict,
        params: dict,
        callbacks=None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """
        基于 validate 结果执行精准增量同步（smart sync）。

        直接消费 validate_kline 的扫描结果，按问题类型分层选择同步策略，
        避免全量重写 Parquet。复用 build_download_plan 分层算法，
        内部调用 DataService.sync() 执行实际同步。

        分层策略：
          Layer A（全量层）：has_cache == False 的标的 → 全量同步
          Layer B（缺口层）：存在 gap_segments / head_gap_segments → 按段精准同步
          Layer C（增量层）：tail_missing > 0 → 增量同步（从最早 tail_start 到今天）

        Args:
            validate_result: validate_kline 的返回字典（含 'results' 列表）
            params: 参数字典，包含：
                period:        str  数据周期，如 '1d'（必填）
                default_start: str  Layer A 全量同步时，若标的无 open_date 则使用此起始日期（YYYYMMDD，可选）
            callbacks: ServiceCallbacks 实例（含 on_progress / on_log / on_error / on_done）
            stop_flag: 停止检查函数，返回 True 时在当前批次完成后停止

        Returns:
            {
                'success':       bool,
                'total_batches': int,
                'done_batches':  int,
                'failed_batches': int,
                'sync_count':    int,   # 同步标的数（去重）
                'skipped_count': int,   # 跳过标的数
                'interrupted':   bool,
                'layer_a_count': int,
                'layer_b_count': int,
                'layer_c_count': int,
            }
        """
        from data_manager.download_handlers import build_download_plan
        from data_manager.asset_types import get_asset_type
        from datetime import datetime

        cb = callbacks or ServiceCallbacks()

        empty_result = {
            'success':        False,
            'total_batches':  0,
            'done_batches':   0,
            'failed_batches': 0,
            'sync_count':     0,
            'skipped_count':  0,
            'interrupted':    False,
            'layer_a_count':  0,
            'layer_b_count':  0,
            'layer_c_count':  0,
        }

        try:
            period        = params.get('period', '1d')
            default_start = params.get('default_start')
            today_str     = datetime.now().strftime('%Y%m%d')

            # ── 1. 获取 SubTypeConfig（stock/kline）──────────────
            at_config  = get_asset_type('stock')
            sub_config = at_config.get_sub_type('kline') if at_config else None
            if sub_config is None:
                msg = "sync_smart：无法获取 stock/kline SubTypeConfig"
                cb.on_error(msg)
                return empty_result

            # ── 2. 生成分层计划（复用 build_download_plan）──────
            results_list = validate_result.get('results', [])
            if not results_list:
                cb.on_log("sync_smart：validate 结果为空，无需同步")
                empty_result['success'] = True
                return empty_result

            plan = build_download_plan(
                validate_results=results_list,
                period=period,
                sub_type_config=sub_config,
                default_start=default_start,
            )

            if plan.total_batches == 0:
                cb.on_log("✅ Parquet 缓存健康，无需同步")
                empty_result['success'] = True
                return empty_result

            # ── 3. 按 Layer A → B → C 顺序执行同步 ──────────────
            total_batches  = plan.total_batches
            done_batches   = 0
            failed_batches = 0
            interrupted    = False
            sync_symbols: set = set()

            all_tasks = (
                [('A', t) for t in plan.layer_a] +
                [('B', t) for t in plan.layer_b] +
                [('C', t) for t in plan.layer_c]
            )

            layer_labels = {
                'A': 'Layer A（全量）',
                'B': 'Layer B（缺口）',
                'C': 'Layer C（增量）',
            }
            current_layer = None

            for layer, task in all_tasks:
                # 检查停止标志
                if stop_flag and stop_flag():
                    interrupted = True
                    cb.on_log("⚠ 收到停止信号，已中断")
                    break

                if layer != current_layer:
                    current_layer = layer
                    cb.on_log(f"\n▶ 开始执行 {layer_labels[layer]}")

                cb.on_log(f"  批次 {done_batches + 1}/{total_batches}：{task.desc}")

                # Layer C 增量同步：start_date 取最早的 tail_start
                if layer == 'C':
                    # 从 validate 结果中找出所有后缺失标的的最早 tail_start
                    tail_starts = [
                        r.get('tail_start')
                        for r in results_list
                        if r.get('has_cache') and r.get('tail_missing', 0) > 0
                        and r.get('tail_start')
                    ]
                    batch_start = min(tail_starts) if tail_starts else None
                    batch_end   = today_str
                else:
                    batch_start = task.start
                    batch_end   = task.end or today_str

                try:
                    batch_result = self.sync(
                        params={
                            'symbols':     task.symbol_list,
                            'periods':     [task.period],
                            'start_date':  batch_start or default_start or '19900101',
                            'end_date':    batch_end,
                        },
                        callbacks=cb,
                        stop_flag=stop_flag,
                    )
                    done_batches += 1
                    if batch_result.get('failed', 0) == 0:
                        sync_symbols.update(task.symbol_list)
                    else:
                        failed_batches += 1
                        cb.on_log(
                            f"  ⚠ 批次部分失败：成功 {batch_result.get('success', 0)} / "
                            f"失败 {batch_result.get('failed', 0)}"
                        )
                        sync_symbols.update(task.symbol_list)  # 部分成功也计入

                except Exception as e:
                    done_batches += 1
                    failed_batches += 1
                    cb.on_log(f"  ⚠ 批次异常：{e}")
                    logger.error(f"sync_smart 批次异常：{e}", exc_info=True)

                cb.on_progress(done_batches, total_batches)

            # ── 4. 汇总结果 ──────────────────────────────────────
            summary = {
                'success':        not interrupted and failed_batches == 0,
                'total_batches':  total_batches,
                'done_batches':   done_batches,
                'failed_batches': failed_batches,
                'sync_count':     len(sync_symbols),
                'skipped_count':  validate_result.get('total', 0) - len(sync_symbols),
                'interrupted':    interrupted,
                'layer_a_count':  len(plan.layer_a_symbols),
                'layer_b_count':  len(plan.layer_b_symbols),
                'layer_c_count':  len(plan.layer_c_symbols),
            }

            cb.on_log(
                f"\nsync_smart {'已中断' if interrupted else '完成'} | "
                f"总批次：{total_batches} | 成功：{done_batches - failed_batches} | "
                f"失败：{failed_batches} | 同步标的：{len(sync_symbols)}"
            )
            cb.on_done(summary)
            return summary

        except Exception as e:
            msg = f'sync_smart 出错：{e}'
            logger.error(msg, exc_info=True)
            cb.on_error(msg)
            cb.on_done(empty_result)
            return empty_result
