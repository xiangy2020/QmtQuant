# -*- coding: utf-8 -*-
"""
scheduler_service.py — 独立后端调度服务（Layer 2）

遵循两层架构规范：
  CLI → SchedulerService (本文件) → DataService → Layer 1

职责：
  - 管理定时数据下载任务的生命周期（start / stop / run_now）
  - 通过 SchedulerCallbacks 回调接口上报状态、日志、错误
- 通过 DataService.download() 执行实际数据下载，不绕过服务层

设计原则：
- 纯 Python，独立可运行
  - 调度循环运行在后台 threading.Thread 中，start() 非阻塞
  - 支持 stop_flag 中断正在执行的 DataService 任务
  - 单次执行失败不停止调度服务，下次定时继续尝试
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

try:
    import schedule as _schedule
except ImportError:
    _schedule = None

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# 调度配置
# ──────────────────────────────────────────────────────────────────

@dataclass
class SchedulerConfig:
    """
    调度任务配置。

    必填字段：
        sector:    板块名称，如 '沪深300'
        periods:   数据周期列表，如 ['1d', '1m']
        run_time:  每日执行时间，格式 'HH:MM'，如 '15:30'

    可选字段：
        asset_type:       一级品类，默认 'stock'
        sub_type:         二级子类，默认 'kline'
        download_mode:  下载模式，'incremental' | 'full' | 'gap'，默认 'incremental'
        check_trade_day:  是否检查交易日，默认 True（非交易日跳过执行）
    """
    sector: str
    periods: List[str]
    run_time: str
    asset_type: str = 'stock'
    sub_type: str = 'kline'
    download_mode: str = 'incremental'
    check_trade_day: bool = True

    def validate(self) -> Optional[str]:
        """
        校验配置合法性。

        Returns:
            None 表示合法；str 表示错误信息。
        """
        if not self.sector or not self.sector.strip():
            return 'sector（板块名称）不能为空'
        if not self.periods:
            return 'periods（数据周期列表）不能为空'
        if not self.run_time or not self.run_time.strip():
            return 'run_time（执行时间）不能为空'
        # 校验 HH:MM 格式
        try:
            parts = self.run_time.strip().split(':')
            if len(parts) != 2:
                raise ValueError
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            return f'run_time 格式不合法：{self.run_time!r}，应为 HH:MM（如 15:30）'
        valid_modes = ('incremental', 'full', 'gap', 'smart')
        if self.download_mode not in valid_modes:
            return f'download_mode 不合法：{self.download_mode!r}，可选値：{valid_modes}'        return None


# ──────────────────────────────────────────────────────────────────
# 回调接口
# ──────────────────────────────────────────────────────────────────

class SchedulerCallbacks:
    """
    调度服务统一回调接口（基类，默认空实现）。

    状态值说明：
        'idle'      — 已启动，等待下次定时触发
        'running'   — 调度循环正在运行（等待触发）
        'executing' — 正在执行数据下载任务
        'stopped'   — 调度服务已停止
    """

    def on_status_changed(self, status: str) -> None:
        """调度服务状态变更回调"""
        pass

    def on_log(self, message: str) -> None:
        """日志回调"""
        pass

    def on_error(self, error: str) -> None:
        """错误回调"""
        pass

    def on_task_done(self, result: dict) -> None:
        """一次完整执行完成回调，result 包含执行摘要"""
        pass

    def on_next_run_updated(self, next_run_time: str) -> None:
        """下次执行时间更新回调，格式 'YYYY-MM-DD HH:MM'"""
        pass


class DefaultSchedulerCallbacks(SchedulerCallbacks):
    """
    默认回调实现，将所有回调输出到 stdout。
供 CLI 场景使用。
    """

    def on_status_changed(self, status: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] [调度状态] {status}')

    def on_log(self, message: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] {message}')

    def on_error(self, error: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] ✗ {error}')

    def on_task_done(self, result: dict) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        success = result.get('success', False)
        mark = '✓' if success else '✗'
        print(f'[{ts}] {mark} 任务完成：{result}')

    def on_next_run_updated(self, next_run_time: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] 下次执行：{next_run_time}')


# ──────────────────────────────────────────────────────────────────
# 调度服务
# ──────────────────────────────────────────────────────────────────

class SchedulerService:
    """
    独立后端调度服务。

    使用示例（CLI 阻塞模式）：
        config = SchedulerConfig(sector='沪深300', periods=['1d'], run_time='15:30')
        svc = SchedulerService()
        svc.start(config)
        try:
            while svc.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            svc.stop()
    """

    def __init__(self):
        self._config: Optional[SchedulerConfig] = None
        self._callbacks: Optional[SchedulerCallbacks] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._task_stop_event = threading.Event()
        self._is_running = False
        self._is_executing = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公开属性
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """调度服务是否正在运行（含等待触发和执行中）"""
        return self._is_running

    @property
    def is_executing(self) -> bool:
        """是否正在执行数据下载任务"""
        return self._is_executing

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def start(
        self,
        config: SchedulerConfig,
        callbacks: Optional[SchedulerCallbacks] = None,
    ) -> None:
        """
        启动调度服务（非阻塞）。

        Args:
            config:    调度配置
            callbacks: 回调接口，不传则使用 DefaultSchedulerCallbacks

        Raises:
            RuntimeError: 服务已在运行时重复调用
            ValueError:   配置校验失败
        """
        with self._lock:
            if self._is_running:
                raise RuntimeError('SchedulerService 已在运行，请先调用 stop() 再重新启动')

            # 校验配置
            err = config.validate()
            if err:
                raise ValueError(f'SchedulerConfig 校验失败：{err}')

            if _schedule is None:
                raise ImportError('缺少依赖：schedule 库未安装，请执行 pip install schedule')

            self._config = config
            self._callbacks = callbacks or DefaultSchedulerCallbacks()
            self._stop_event.clear()
            self._task_stop_event.clear()
            self._is_running = True

        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name='SchedulerService-Loop',
            daemon=True,
        )
        self._thread.start()
        cb = self._callbacks
        cb.on_log(
            f'调度服务已启动 | 板块：{config.sector} | '
            f'周期：{", ".join(config.periods)} | '
            f'执行时间：{config.run_time} | '
            f'模式：{config.download_mode}'
        )
        cb.on_status_changed('running')

    def stop(self, timeout: float = 300.0) -> None:
        """
        停止调度服务，等待当前任务完成后退出。

        Args:
            timeout: 等待当前任务完成的最长秒数，默认 300 秒
        """
        with self._lock:
            if not self._is_running:
                return
            self._stop_event.set()
            self._task_stop_event.set()  # 通知正在执行的 DataService 任务停止

        cb = self._callbacks
        if cb:
            cb.on_log('正在停止调度服务，等待当前任务完成...')

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        with self._lock:
            self._is_running = False
            self._is_executing = False

        if cb:
            cb.on_status_changed('stopped')
            cb.on_log('调度服务已停止')

    def run_now(self) -> None:
        """
        立即触发一次数据下载任务（在独立线程中执行，不影响定时计划）。

        如果服务未启动，则使用 DefaultSchedulerCallbacks 执行一次性任务。
        """
        if not self._config:
            raise RuntimeError('请先调用 start() 或设置 config 后再调用 run_now()')

        cb = self._callbacks or DefaultSchedulerCallbacks()
        cb.on_log('手动触发：立即执行数据下载')

        t = threading.Thread(
            target=self._execute_task,
            name='SchedulerService-RunNow',
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------
    # 内部调度循环
    # ------------------------------------------------------------------

    def _scheduler_loop(self) -> None:
        """后台调度循环（在独立线程中运行）"""
        config = self._config
        cb = self._callbacks

        # 清空旧任务，设置新任务
        _schedule.clear('scheduler_service')
        for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
            getattr(_schedule.every(), day).at(config.run_time).do(
                self._check_and_execute
            ).tag('scheduler_service')

        # 上报下次执行时间
        self._notify_next_run()

        cb.on_log(f'调度循环已就绪，每个工作日 {config.run_time} 触发')
        cb.on_status_changed('idle')

        while not self._stop_event.is_set():
            _schedule.run_pending()
            # 每次 run_pending 后更新下次执行时间
            self._notify_next_run()
            # 每秒检查一次
            self._stop_event.wait(timeout=1.0)

        _schedule.clear('scheduler_service')
        logger.info('SchedulerService 调度循环已退出')

    def _notify_next_run(self) -> None:
        """上报下次执行时间"""
        try:
            jobs = [j for j in _schedule.jobs if 'scheduler_service' in j.tags]
            if jobs:
                next_run = min(j.next_run for j in jobs)
                if next_run:
                    self._callbacks.on_next_run_updated(
                        next_run.strftime('%Y-%m-%d %H:%M')
                    )
        except Exception:
            pass

    def _check_and_execute(self) -> None:
        """检查是否为交易日，是则执行任务"""
        config = self._config
        cb = self._callbacks
        today_str = datetime.now().strftime('%Y-%m-%d')

        if config.check_trade_day:
            try:
                from utils import is_trade_day
                if not is_trade_day(today_str):
                    cb.on_log(f'今日 {today_str} 非交易日，跳过')
                    return
            except Exception as e:
                cb.on_log(f'交易日检查失败（{e}），直接执行')

        cb.on_log(f'今日 {today_str} 为交易日，开始执行数据下载')
        self._execute_task()

    def _execute_task(self) -> None:
        """
        执行一次完整的数据下载任务。

按 periods 顺序逐一调用 DataService.download()，
        将进度/日志通过 SchedulerCallbacks.on_log() 转发。
        单次执行失败不停止调度服务。
        """
        config = self._config
        cb = self._callbacks

        with self._lock:
            if self._is_executing:
                cb.on_log('上一次任务仍在执行中，跳过本次触发')
                return
            self._is_executing = True
            self._task_stop_event.clear()

        cb.on_status_changed('executing')
        start_time = datetime.now()
        cb.on_log(f'── 开始执行数据下载 [{start_time.strftime("%Y-%m-%d %H:%M:%S")}] ──')

        overall_success = True
        period_results = []

        try:
            # 加载 DataService
            try:
                from data_manager.data_service import DataService, ServiceCallbacks
            except ImportError as e:
                cb.on_error(f'无法导入 DataService：{e}')
                overall_success = False
                return

            # 获取板块成分股
            try:
                from env import xtdata
                stock_list = xtdata.get_stock_list_in_sector(config.sector)
                if not stock_list:
                    cb.on_error(f'板块 "{config.sector}" 成分股为空，请检查板块名称')
                    overall_success = False
                    return
                cb.on_log(f'板块 "{config.sector}" 共 {len(stock_list)} 只标的')
            except Exception as e:
                cb.on_error(f'获取板块成分股失败：{e}')
                overall_success = False
                return

            service = DataService()

            # 按周期顺序逐一执行
            for period in config.periods:
                if self._task_stop_event.is_set():
                    cb.on_log(f'收到停止信号，跳过剩余周期')
                    overall_success = False
                    break

                cb.on_log(f'── 补充 {period} 数据 ──')

                # 构建 DataService 回调适配器
                class _TaskCallbacks(ServiceCallbacks):
                    def __init__(self, outer_cb):
                        self._cb = outer_cb

                    def on_progress(self, done: int, total: int) -> None:
                        pct = int(done / total * 100) if total > 0 else 0
                        self._cb.on_log(f'  进度：{done}/{total} ({pct}%)')

                    def on_log(self, message: str) -> None:
                        self._cb.on_log(f'  {message}')

                    def on_error(self, error: str) -> None:
                        self._cb.on_error(f'  {error}')

                    def on_done(self, result: dict) -> None:
                        pass  # 由外层统一处理

                params = {
                    'stock_list': stock_list,
                    'period_type': period,
                    'mode': config.download_mode,
                    'asset_type': config.asset_type,
                    'sub_type': config.sub_type,
                }

                stop_flag = lambda: self._task_stop_event.is_set()

                try:
                    result = service.download(
                        params=params,
                        callbacks=_TaskCallbacks(cb),
                        stop_flag=stop_flag,
                    )
                    period_results.append({'period': period, 'result': result})
                    if result.get('success'):
                        cb.on_log(f'  ✓ {period} 下载完成')
                    else:
                        cb.on_log(f'  ✗ {period} 下载失败：{result.get("message", "")}')
                        overall_success = False
                except Exception as e:
                    msg = f'{period} 下载出错：{e}'
                    cb.on_error(msg)
                    logger.error(msg, exc_info=True)
                    period_results.append({'period': period, 'error': str(e)})
                    overall_success = False

        finally:
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            summary = {
                'success': overall_success,
                'sector': config.sector,
                'periods': config.periods,
                'period_results': period_results,
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'elapsed_seconds': round(elapsed, 1),
                'interrupted': self._task_stop_event.is_set(),
            }
            mark = '✓' if overall_success else '✗'
            cb.on_log(
                f'── {mark} 数据下载完成 [{end_time.strftime("%H:%M:%S")}] '
                f'耗时 {elapsed:.0f}s ──'
            )
            cb.on_task_done(summary)

            with self._lock:
                self._is_executing = False

            # 恢复 idle 状态（仅在调度服务仍在运行时）
            if self._is_running:
                cb.on_status_changed('idle')
                self._notify_next_run()
