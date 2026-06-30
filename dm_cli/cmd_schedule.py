# -*- coding: utf-8 -*-
"""
dm_cli/cmd_schedule.py — schedule 子命令实现

包含：_CliSchedulerCallbacks、cmd_schedule
"""

import sys
import time
from datetime import datetime

from dm_cli.common import (
    _ok, _warn, _err, _info, _header,
    _RESET, _GREEN, _YELLOW, _RED, _CYAN, _BOLD,
)


class _CliSchedulerCallbacks:
    """将 SchedulerService 回调输出到终端（含颜色、时间戳），与现有 CLI 风格一致"""

    def on_status_changed(self, status: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        status_map = {
            'running':   f'{_CYAN}运行中（等待触发）{_RESET}',
            'idle':      f'{_CYAN}空闲（等待触发）{_RESET}',
            'executing': f'{_YELLOW}执行中{_RESET}',
            'stopped':   f'{_RESET}已停止{_RESET}',
        }
        label = status_map.get(status, status)
        print(f'[{ts}] {_CYAN}[调度]{_RESET} 状态变更 → {label}')

    def on_log(self, message: str) -> None:
        _info(message)

    def on_error(self, error: str) -> None:
        _err(error)

    def on_task_done(self, result: dict) -> None:
        success = result.get('success', False)
        elapsed = result.get('elapsed_seconds', 0)
        if success:
            _ok(f"任务完成，耗时 {elapsed:.0f}s")
        else:
            _warn(f"任务完成（有失败），耗时 {elapsed:.0f}s")

    def on_next_run_updated(self, next_run_time: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] {_CYAN}[调度]{_RESET} 下次执行：{next_run_time}')


def cmd_schedule(args):
    """定时调度（持续运行 / 立即执行一次）"""
    from data_manager.scheduler_service import SchedulerConfig, SchedulerService

    asset = (getattr(args, 'asset', None) or 'stock').strip()
    sub   = (getattr(args, 'sub',   None) or 'kline').strip()

    # 校验必填参数
    if not getattr(args, 'sector', None):
        _err('schedule 命令需要 --sector 参数（板块名称，如 沪深300）')
        sys.exit(1)

    if not getattr(args, 'period', None):
        _err('schedule 命令需要 --period 参数（数据周期，如 1d）')
        sys.exit(1)

    periods = [p.strip() for p in args.period.split(',') if p.strip()]
    run_time = getattr(args, 'time', '15:30') or '15:30'
    mode = getattr(args, 'mode', 'incremental') or 'incremental'
    run_now = getattr(args, 'run_now', False)
    no_exit = getattr(args, 'no_exit', False)

    config = SchedulerConfig(
        sector=args.sector,
        periods=periods,
        run_time=run_time,
        asset_type=asset,
        sub_type=sub,
        download_mode=mode,
        check_trade_day=True,
    )

    # 校验配置
    err = config.validate()
    if err:
        _err(f'配置错误：{err}')
        sys.exit(1)

    callbacks = _CliSchedulerCallbacks()
    svc = SchedulerService()

    _header(
        f'📅 定时调度 | 板块：{args.sector} | '
        f'周期：{", ".join(periods)} | '
        f'时间：{run_time} | 模式：{mode}'
    )
    print()

    if run_now and not no_exit:
        # 立即执行一次后退出
        _info('立即执行一次数据下载（--run-now 模式）...')
        svc._config = config
        svc._callbacks = callbacks
        svc._execute_task()
        _ok('执行完成，退出')
        return

    # 启动调度服务
    svc.start(config, callbacks=callbacks)

    if run_now and no_exit:
        # 立即执行一次，然后继续调度
        _info('立即执行一次数据下载（--run-now --no-exit 模式）...')
        svc.run_now()

    _info(f'调度服务已启动，按 Ctrl+C 停止')
    print()

    try:
        while svc.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        _warn('收到 Ctrl+C，正在优雅停止调度服务...')
        svc.stop(timeout=300)
        _ok('调度服务已停止')
