# coding: utf-8
"""
framework/callbacks.py — 框架回调协议定义

框架核心（framework/core.py / framework/backtest_mixin.py）通过本模块定义的
FrameworkCallbacks 协议与外部（CLI / 测试）通信。

调用方只需实现本协议即可对接框架：
  - CLI：CliFrameworkCallbacks（见 bt_cli.py）
  - 测试：自定义 Mock 实现
"""

from __future__ import annotations

import datetime
from typing import runtime_checkable

try:
    from typing import Protocol
except ImportError:  # Python < 3.8 兜底
    from typing_extensions import Protocol  # type: ignore

@runtime_checkable
class FrameworkCallbacks(Protocol):
    """
    框架回调协议。

    框架核心通过此协议向外部传递日志、进度、交互请求等事件，
    外部（CLI / 测试）实现此协议后传入框架即可。
    """

    def on_log(self, message: str, level: str = "INFO") -> None:
        """
        日志回调。

        :param message: 日志内容
        :param level:   日志级别，可选值：DEBUG / INFO / WARNING / ERROR / TRADE
        """
        ...

    def on_progress(self, pct: int) -> None:
        """
        进度回调（0-100）。

        :param pct: 当前进度百分比
        """
        ...

    def on_period_mismatch(self, message: str) -> bool:
        """
        数据周期与触发类型不匹配时的交互回调。

        框架将不匹配详情通过 message 传入，由调用方决定是否继续运行。

        :param message: 不匹配详情描述
        :return: True = 继续运行；False = 停止运行
        """
        ...

    def on_t0_warning(self, message: str) -> None:
        """
        T+0 混合池警告回调。

        :param message: 警告内容
        """
        ...

    def on_finished(self) -> None:
        """框架运行完成回调。"""
        ...

class DefaultCallbacks:
    """
    FrameworkCallbacks 的默认实现。

    - on_log：将日志打印到 stdout
    - on_progress：静默忽略
    - on_period_mismatch：打印警告后默认返回 True（继续运行，不阻塞）
    - on_t0_warning：打印警告到 stdout
    - on_finished：静默忽略

    框架未收到 callbacks 参数时自动使用此实现，
    可在无任何外部依赖的情况下独立运行。
    """

    def on_log(self, message: str, level: str = "INFO") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{level}] {ts}  {message}")

    def on_progress(self, pct: int) -> None:
        pass  # 默认静默

    def on_period_mismatch(self, message: str) -> bool:
        print(f"[WARNING] 数据周期与触发类型不匹配，默认继续运行：\n{message}")
        return True  # 默认继续

    def on_t0_warning(self, message: str) -> None:
        print(f"[WARNING] T+0 模式警告：{message}")

    def on_finished(self) -> None:
        pass  # 默认静默
