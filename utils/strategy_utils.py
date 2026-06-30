# -*- coding: utf-8 -*-
"""
utils/strategy_utils.py — 策略工具函数（moving_avg、信号生成等）
"""

import logging
import math
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional

import pandas as pd

from env import xtdata
from utils.stock_utils import get_price_decimals, is_etf, is_trade_time


def get_history(
    symbol_list: str | List[str],
    fields: List[str],
    bar_count: int,
    fre_step: str,
    current_time: Optional[str] = None,
    skip_paused: bool = False,
    fq: str = 'pre',
    force_download: bool = False,
) -> Dict:
    """获取历史K线数据

    封装 xtdata.get_market_data_ex，提供策略友好的调用接口。

    Args:
        symbol_list: 股票代码或代码列表
        fields: 字段列表，如 ['close', 'volume']
        bar_count: 拉取的K线根数
        fre_step: 频率，如 '1d', '1m', '5m'
        current_time: 结束时间点，格式取决于 fre_step
                      '1d' → 'YYYYMMDD'
                      '1m'/'5m' → 'YYYYMMDDHHMMSS'
                      为 None 时使用当前时间
        skip_paused: 是否跳过停牌日期（保留参数，暂未实现）
        fq: 复权方式，'pre'=前复权, 'post'=后复权, 'none'=不复权
        force_download: 是否强制下载（保留参数，暂未实现）

    Returns:
        dict: {stock_code: DataFrame}，DataFrame 索引为时间，列为请求的 fields
    """
    # 复权映射
    dividend_map = {'pre': 'front_ratio', 'post': 'back_ratio', 'none': 'none'}
    dividend_type = dividend_map.get(fq, 'none')

    # 归一化 symbol_list
    if isinstance(symbol_list, str):
        symbols = [symbol_list]
    else:
        symbols = list(symbol_list)

    # 时间处理
    if current_time is None:
        now = datetime.now()
        if fre_step in ('1m', '5m', 'tick'):
            current_time = now.strftime('%Y%m%d%H%M%S')
        else:
            current_time = now.strftime('%Y%m%d')

    # 使用 count 参数拉取最近 bar_count 根K线
    data = xtdata.get_market_data_ex(
        field_list=fields,
        stock_list=symbols,
        period=fre_step,
        start_time='',
        end_time=current_time,
        count=bar_count,
        dividend_type=dividend_type,
        fill_data=True,
    )

    if not data:
        return {}

    return data


def moving_avg(
    stock_code: str,
    period: int,
    field: str = 'close',
    fre_step: str = '1d',
    end_time: Optional[str] = None,
    fq: str = 'pre',
    data: Dict = None,
) -> float:
    """计算移动平均线

    Args:
        stock_code: 股票代码
        period: 周期长度
        field: 计算字段，默认为'close'
        fre_step: 时间频率，如'1d', '1m'等
        end_time: 结束时间，如果为None使用当前时间
        fq: 复权方式，'pre'前复权, 'post'后复权, 'none'不复权
        data: 策略接收的数据对象，用于获取精度设置（可选）

    Returns:
        float: 移动平均值
    """

    if end_time is None:
        now = datetime.now()
        if fre_step in ['1m', '5m', 'tick']:
            end_time = now.strftime('%Y%m%d %H%M%S')
        else:
            end_time = now.strftime('%Y%m%d')

    if fre_step in ['1m', '5m', 'tick'] and not is_trade_time():
        raise ValueError("不在交易时间内，无法计算日内移动平均线")

    history_data = get_history(
        symbol_list=stock_code,
        fields=[field],
        bar_count=period,
        fre_step=fre_step,
        current_time=end_time,
        fq=fq,
        force_download=False,
    )

    if stock_code not in history_data or len(history_data[stock_code]) < period:
        raise ValueError(f"股票 {stock_code} 数据量不足 {period} 条，无法计算均线{period}")

    prices = history_data[stock_code][field]
    decimals = get_price_decimals(data) if data else (3 if is_etf(stock_code) else 2)
    return round(prices.mean(), decimals)


def calculate_max_buy_volume(
    data: Dict,
    stock_code: str,
    price: float,
    cash_ratio: float = 1.0,
) -> int:
    """计算最大可买入数量，考虑交易成本（包括滑点）

    Args:
        data: 策略接收的数据对象，包含账户信息 __account__ 和框架信息 __framework__
        stock_code: 股票代码
        price: 当前价格
        cash_ratio: 使用可用资金的比例，默认为1.0表示使用全部可用资金

    Returns:
        int: 最大可买入股数(按手取整)
    """
    try:
        account_info = data.get("__account__", {})
        if not account_info:
            logging.warning("无法获取账户信息，无法计算最大买入量")
            return 0

        available_cash = account_info.get("cash", 0.0)
        usable_cash = available_cash * cash_ratio

        if price <= 0:
            logging.warning(f"股票 {stock_code} 价格异常: {price}，无法计算买入量")
            return 0

        decimals = get_price_decimals(data)
        price = round(price, decimals)

        # 优先尝试使用实盘 TradeManager（含滑点/手续费精确计算）
        try:
            from trade import TradeManager

            framework = data.get("__framework__", None)
            if framework and hasattr(framework, 'config'):
                config = framework.config
            else:
                config = SimpleNamespace(config_dict={"backtest": {"trade_cost": {}}})

            trade_manager = TradeManager(config)
            commission_rate = trade_manager.commission_rate
            transfer_fee_rate = 0.00001 if stock_code.startswith("sh.") else 0.0

            estimated_shares = math.floor(
                usable_cash / price / (1 + commission_rate + transfer_fee_rate)
            )
            shares = math.floor(estimated_shares / 100) * 100

            if shares < 100:
                return 0

            while shares >= 100:
                actual_price, trade_cost = trade_manager.calculate_trade_cost(
                    price=price,
                    volume=shares,
                    direction="buy",
                    stock_code=stock_code,
                )
                total_cost = actual_price * shares + trade_cost

                if total_cost <= usable_cash:
                    logging.info(
                        f"计算买入量: 股票={stock_code}, 原始价格={price:.{decimals}f}, "
                        f"考虑滑点后价格={actual_price:.{decimals}f}, "
                        f"可用现金={available_cash:.{decimals}f}, 使用比例={cash_ratio:.2f}, "
                        f"计划买入={shares}, 成本={trade_cost:.2f}, 总花费={total_cost:.{decimals}f}"
                    )
                    return int(shares)

                shares -= 100

            return 0

        except ImportError:
            # 回测模式：trade 模块不可用，直接按资金/价格估算（含万3手续费）
            COMMISSION_RATE = 0.0003  # 万3
            estimated_shares = math.floor(
                usable_cash / price / (1 + COMMISSION_RATE)
            )
            shares = math.floor(estimated_shares / 100) * 100
            if shares < 100:
                return 0
            logging.info(
                f"计算买入量(回测): 股票={stock_code}, 价格={price:.{decimals}f}, "
                f"可用现金={available_cash:.2f}, 使用比例={cash_ratio:.2f}, 可买={shares}股"
            )
            return int(shares)

    except Exception as e:
        logging.error(f"计算最大可买入数量时出错: {str(e)}", exc_info=True)
        return 0


def generate_signal(
    data: Dict,
    stock_code: str,
    price: float,
    ratio: float,
    action: str,
    reason: str = "",
) -> List[Dict]:
    """生成标准交易信号

    Args:
        data: 包含时间、账户、持仓信息的字典，以及框架信息 __framework__
        stock_code: 股票代码
        price: 交易价格
        ratio: 当ratio≤1时表示交易比例；当ratio>1时表示买入的股数（必须是100的整数倍）
        action: 'buy' 或 'sell'
        reason: 交易原因

    Returns:
        List[Dict]: 包含单个信号的列表，或空列表
    """
    signals = []
    current_time = data.get("__current_time__", {})
    timestamp = current_time.get("timestamp")

    decimals = get_price_decimals(data)
    price = round(price, decimals)

    if action == "buy":
        if ratio > 1:
            target_volume = int(ratio)
            if target_volume % 100 != 0:
                logging.error(f"买入股数必须是100的整数倍: 股票={stock_code}, 输入股数={target_volume}")
                return []

            max_volume = calculate_max_buy_volume(data, stock_code, price, cash_ratio=1.0)
            if max_volume == 0:
                logging.warning(
                    f"无法生成买入信号: 股票={stock_code}, 价格={price:.{decimals}f}, "
                    f"目标股数={target_volume}, 但资金不足无法买入"
                )
                return []
            elif target_volume > max_volume:
                logging.warning(
                    f"目标买入量超过最大可买入量: 股票={stock_code}, 目标={target_volume}, "
                    f"最大可买={max_volume}, 将调整为最大可买入量"
                )
                actual_volume = max_volume
            else:
                actual_volume = target_volume

            signal = {
                "code": stock_code,
                "action": "buy",
                "price": price,
                "volume": actual_volume,
                "reason": reason or f"按价格 {price:.{decimals}f} 买入 {actual_volume}股({actual_volume//100}手)",
            }
            if timestamp:
                signal["timestamp"] = timestamp
            signals.append(signal)
            logging.info(f"生成买入信号: {signal}")
        else:
            max_volume = calculate_max_buy_volume(data, stock_code, price, cash_ratio=ratio)
            if max_volume > 0:
                signal = {
                    "code": stock_code,
                    "action": "buy",
                    "price": price,
                    "volume": max_volume,
                    "reason": reason or f"按价格 {price:.{decimals}f} 以 {ratio*100:.0f}% 资金比例买入",
                }
                if timestamp:
                    signal["timestamp"] = timestamp
                signals.append(signal)
                logging.info(f"生成买入信号: {signal}")
            else:
                logging.warning(
                    f"无法生成买入信号: 股票={stock_code}, 价格={price:.{decimals}f}, "
                    f"资金比例={ratio:.2f}, 计算可买量为0"
                )

    elif action == "sell":
        positions_info = data.get("__positions__", {})
        if stock_code in positions_info:
            position_data = positions_info[stock_code]
            available_volume = position_data.get("can_use_volume", position_data.get("volume", 0))

            if available_volume > 0:
                sell_volume = math.floor((available_volume * ratio) / 100) * 100
                if sell_volume > 0:
                    signal = {
                        "code": stock_code,
                        "action": "sell",
                        "price": price,
                        "volume": int(sell_volume),
                        "reason": reason or f"按价格 {price:.{decimals}f} 卖出 {ratio*100:.0f}% 可用持仓",
                    }
                    if timestamp:
                        signal["timestamp"] = timestamp
                    signals.append(signal)
                    logging.info(f"生成卖出信号: {signal}")
                else:
                    logging.warning(
                        f"无法生成卖出信号: 股票={stock_code}, 价格={price:.{decimals}f}, "
                        f"持仓比例={ratio:.2f}, 计算可卖量为0 (可用持仓={available_volume})"
                    )
            else:
                logging.warning(f"无法生成卖出信号: 股票={stock_code} 无可用持仓")
        else:
            logging.warning(f"无法生成卖出信号: 股票={stock_code} 不在持仓中")

    return signals


class StopLossManager:
    """通用止损止盈管理器

    封装两个粒度的止损止盈：
      - 标的粒度：固定止损、固定止盈、追踪止损（移动止损）、移动止盈（追踪止盈）、时间止损
      - 组合粒度：组合止损、组合追踪止损、组合止盈（以整体净值为基准，触发则全部清仓）

    内部自动管理跨 bar 的状态（最高价、建仓时间、组合净值基准等），策略只需在 init()
    中实例化一次，在 on_bar() 中调用 check(data) 即可完成所有持仓的止损止盈检查。

    Args:
        stop_loss:                  固定止损比例，如 0.05 表示跌超5%止损；None 表示不启用
        stop_profit:                固定止盈比例，如 0.20 表示涨超20%止盈；None 表示不启用
        trailing_stop:              追踪止损回撤比例，如 0.08 表示从最高价回撤8%止损；None 表示不启用
        trailing_profit_activate:   移动止盈激活阈值，如 0.10 表示盈利达10%后开始追踪；None 表示不启用
        trailing_profit_callback:   移动止盈回撤比例，如 0.05 表示从盈利高点回落5%止盈；None 表示不启用
        time_stop_days:             时间止损天数，如 15 表示持仓15个自然日未盈利则卖出；None 表示不启用
        portfolio_stop_loss:        组合止损比例，如 0.08 表示调仓后净值下跌8%全部清仓；None 表示不启用
        portfolio_trailing_stop:    组合追踪止损比例，如 0.10 表示净值从最高点回撤10%全部清仓；None 表示不启用
        portfolio_stop_profit:      组合止盈比例，如 0.30 表示整体盈利30%全部清仓；None 表示不启用
        price_field:                获取价格时使用的字段，默认 "open"（回测场景避免未来函数）

    典型用法::

        # init() 中初始化一次
        def init(stocks=None, data=None):
            global stop_manager
            stop_manager = StopLossManager(
                # ── 标的粒度 ──────────────────────────────────────────
                stop_loss=0.05,
                stop_profit=0.20,
                trailing_stop=0.08,
                trailing_profit_activate=0.10,
                trailing_profit_callback=0.05,
                time_stop_days=15,
                # ── 组合粒度 ──────────────────────────────────────────
                portfolio_stop_loss=0.08,
                portfolio_trailing_stop=0.10,
                portfolio_stop_profit=0.30,
            )

        # on_bar() 中一行调用
        def on_bar(data: Dict) -> List[Dict]:
            signals = []
            signals.extend(stop_manager.check(data))
            return signals
    """

    def __init__(
        self,
        stop_loss: Optional[float] = None,
        stop_profit: Optional[float] = None,
        trailing_stop: Optional[float] = None,
        trailing_profit_activate: Optional[float] = None,
        trailing_profit_callback: Optional[float] = None,
        time_stop_days: Optional[int] = None,
        portfolio_stop_loss: Optional[float] = None,
        portfolio_trailing_stop: Optional[float] = None,
        portfolio_stop_profit: Optional[float] = None,
        price_field: str = "open",
    ):
        # ── 标的粒度参数 ──────────────────────────────────────────────
        self.stop_loss = stop_loss
        self.stop_profit = stop_profit
        self.trailing_stop = trailing_stop
        self.trailing_profit_activate = trailing_profit_activate
        self.trailing_profit_callback = trailing_profit_callback
        self.time_stop_days = time_stop_days
        # ── 组合粒度参数 ──────────────────────────────────────────────
        self.portfolio_stop_loss = portfolio_stop_loss
        self.portfolio_trailing_stop = portfolio_trailing_stop
        self.portfolio_stop_profit = portfolio_stop_profit
        # ── 通用参数 ──────────────────────────────────────────────────
        self.price_field = price_field

        # ── 标的粒度内部状态 ──────────────────────────────────────────
        # 追踪止损：记录每只持仓股票的历史最高价 {stock_code: float}
        self._trailing_high: Dict[str, float] = {}
        # 时间止损：记录每只持仓股票的建仓日期（"YYYYMMDD" 格式）{stock_code: str}
        self._entry_date: Dict[str, str] = {}
        # 移动止盈：激活标志 {stock_code: bool}
        self._tp_activated: Dict[str, bool] = {}
        # 移动止盈：盈利最高价 {stock_code: float}，未激活时为 None
        self._tp_high: Dict[str, Optional[float]] = {}

        # ── 组合粒度内部状态 ──────────────────────────────────────────
        # 组合止损基准净值（每次调仓后重置；None 表示尚未初始化）
        self._portfolio_base_value: Optional[float] = None
        # 组合追踪止损：历史最高净值（只升不降）
        self._portfolio_peak_value: Optional[float] = None
        # 组合止盈：策略启动时的初始净值（仅记录一次）
        self._portfolio_init_value: Optional[float] = None
        # 上一个 bar 的持仓快照（用于检测是否发生了交易）{stock_code: volume}
        self._last_positions_snapshot: Dict[str, int] = {}

    # ──────────────────────────────────────────────────────────────────
    # 内部：日志输出
    # ──────────────────────────────────────────────────────────────────

    def _log(self, data: Dict, message: str, level: str = "WARNING") -> None:
        """通过框架回调输出日志，兜底使用 logging。"""
        try:
            fw = data.get("__framework__")
            if fw is not None and hasattr(fw, "_log"):
                fw._log(message, level)
                return
        except Exception:
            pass
        logging.warning(message)

    # ──────────────────────────────────────────────────────────────────
    # 内部：标的粒度状态自动同步
    # ──────────────────────────────────────────────────────────────────

    def _sync_state(self, positions: Dict, current_date: str) -> None:
        """对比当前持仓与内部状态，自动初始化新增持仓、清除已清仓股票的状态。

        Args:
            positions:    当前持仓字典，键为股票代码
            current_date: 当前 bar 日期，"YYYYMMDD" 格式，用于记录建仓日期
        """
        current_codes = set(positions.keys())
        tracked_codes = (
            set(self._trailing_high.keys())
            | set(self._entry_date.keys())
            | set(self._tp_activated.keys())
        )

        # 新增持仓：初始化所有内部状态
        for code in current_codes - tracked_codes:
            avg_price = positions[code].get("avg_price", 0.0)
            # 追踪止损：以成本价作为初始最高价
            self._trailing_high[code] = avg_price if avg_price > 0 else 0.0
            # 时间止损：记录建仓日期
            self._entry_date[code] = current_date
            # 移动止盈：初始化为未激活
            self._tp_activated[code] = False
            self._tp_high[code] = None

        # 已清仓：清除所有内部状态，防止状态残留
        for code in tracked_codes - current_codes:
            self._trailing_high.pop(code, None)
            self._entry_date.pop(code, None)
            self._tp_activated.pop(code, None)
            self._tp_high.pop(code, None)

    # ──────────────────────────────────────────────────────────────────
    # 内部：组合粒度净值计算与状态管理
    # ──────────────────────────────────────────────────────────────────

    def _calc_portfolio_value(self, data: Dict, positions: Dict) -> float:
        """计算当前组合净值 = 持仓市值 + 现金。

        Args:
            data:      策略数据字典
            positions: 当前持仓字典

        Returns:
            float: 当前组合净值；若无法获取账户信息则返回 0.0
        """
        # 延迟导入，避免循环依赖
        from utils.quant_import import get_price as _get_price  # noqa: PLC0415

        # 获取现金
        account = data.get("__account__", {})
        cash: float = account.get("cash", 0.0)

        # 计算持仓市值
        market_value: float = 0.0
        for stock, pos_info in positions.items():
            volume: int = pos_info.get("volume", 0)
            if volume <= 0:
                continue
            price: float = _get_price(data, stock, self.price_field)
            if price > 0:
                market_value += price * volume

        return cash + market_value

    def _detect_trade(self, positions: Dict) -> bool:
        """检测本 bar 是否发生了交易（持仓快照与上一 bar 不同）。

        同时更新持仓快照。

        Args:
            positions: 当前持仓字典

        Returns:
            bool: True 表示发生了交易（持仓有变化）
        """
        # 构建当前快照 {stock_code: volume}
        current_snapshot: Dict[str, int] = {
            code: info.get("volume", 0)
            for code, info in positions.items()
        }

        trade_happened = current_snapshot != self._last_positions_snapshot
        self._last_positions_snapshot = current_snapshot
        return trade_happened

    def _update_portfolio_state(self, current_value: float, trade_happened: bool) -> None:
        """更新组合粒度内部状态。

        - 首次调用：初始化 base / peak / init 三个基准值
        - 发生交易：重置 base（组合止损基准）为当前净值
        - 每次：更新 peak（只升不降）

        Args:
            current_value:  当前组合净值
            trade_happened: 本 bar 是否发生了交易
        """
        if self._portfolio_base_value is None:
            # 首次调用：初始化所有基准值
            self._portfolio_base_value = current_value
            self._portfolio_peak_value = current_value
            self._portfolio_init_value = current_value
            return

        if trade_happened:
            # 发生交易：重置组合止损基准
            self._portfolio_base_value = current_value

        # 更新历史最高净值（只升不降）
        if self._portfolio_peak_value is None or current_value > self._portfolio_peak_value:
            self._portfolio_peak_value = current_value

    # ──────────────────────────────────────────────────────────────────
    # 内部：组合粒度止损止盈检查（触发则全部清仓）
    # ──────────────────────────────────────────────────────────────────

    def _build_liquidate_signals(
        self, data: Dict, positions: Dict, reason: str
    ) -> List[Dict]:
        """对所有持仓生成全仓卖出信号。

        Args:
            data:      策略数据字典
            positions: 当前持仓字典
            reason:    卖出原因

        Returns:
            List[Dict]: 所有持仓的卖出信号列表
        """
        from utils.quant_import import get_price as _get_price  # noqa: PLC0415

        signals: List[Dict] = []
        for stock in positions:
            price: float = _get_price(data, stock, self.price_field)
            if price <= 0:
                continue
            signals.extend(generate_signal(data, stock, price, 1.0, "sell", reason))
        return signals

    def _check_portfolio_stop_loss(
        self, data: Dict, positions: Dict, current_value: float
    ) -> List[Dict]:
        """组合止损检查：当前净值相对基准净值跌幅 >= portfolio_stop_loss 则全部清仓。"""
        if self.portfolio_stop_loss is None or self._portfolio_base_value is None:
            return []
        if self._portfolio_base_value <= 0:
            return []

        drawdown = (current_value - self._portfolio_base_value) / self._portfolio_base_value
        if drawdown <= -self.portfolio_stop_loss:
            reason = f"组合止损清仓 | 净值跌幅: {drawdown:.2%}"
            self._log(data, f"🔴 组合止损触发 | 当前净值: {current_value:.2f}  基准净值: {self._portfolio_base_value:.2f}  {reason}")
            return self._build_liquidate_signals(data, positions, reason)
        return []

    def _check_portfolio_trailing_stop(
        self, data: Dict, positions: Dict, current_value: float
    ) -> List[Dict]:
        """组合追踪止损检查：当前净值相对历史最高净值回撤 >= portfolio_trailing_stop 则全部清仓。"""
        if self.portfolio_trailing_stop is None or self._portfolio_peak_value is None:
            return []
        if self._portfolio_peak_value <= 0:
            return []

        drawdown = (current_value - self._portfolio_peak_value) / self._portfolio_peak_value
        if drawdown <= -self.portfolio_trailing_stop:
            reason = (
                f"组合追踪止损清仓 | 当前净值: {current_value:.2f} "
                f"最高净值: {self._portfolio_peak_value:.2f} "
                f"回撤: {drawdown:.2%}"
            )
            self._log(data, f"🔴 组合追踪止损触发 | {reason}")
            return self._build_liquidate_signals(data, positions, reason)
        return []

    def _check_portfolio_stop_profit(
        self, data: Dict, positions: Dict, current_value: float
    ) -> List[Dict]:
        """组合止盈检查：当前净值相对初始净值盈利 >= portfolio_stop_profit 则全部清仓。"""
        if self.portfolio_stop_profit is None or self._portfolio_init_value is None:
            return []
        if self._portfolio_init_value <= 0:
            return []

        gain = (current_value - self._portfolio_init_value) / self._portfolio_init_value
        if gain >= self.portfolio_stop_profit:
            reason = f"组合止盈清仓 | 盈利: +{gain:.2%}"
            self._log(data, f"🟢 组合止盈触发 | 当前净值: {current_value:.2f}  初始净值: {self._portfolio_init_value:.2f}  {reason}")
            return self._build_liquidate_signals(data, positions, reason)
        return []

    # ──────────────────────────────────────────────────────────────────
    # 内部：标的粒度各类型检查方法
    # ──────────────────────────────────────────────────────────────────

    def _check_stop_loss(
        self, data: Dict, stock: str, price: float, avg_price: float
    ) -> List[Dict]:
        """固定止损检查：亏损超过 stop_loss 比例则全仓卖出。"""
        if self.stop_loss is None or avg_price <= 0:
            return []
        pnl = (price - avg_price) / avg_price
        if pnl <= -self.stop_loss:
            sign = "+" if pnl >= 0 else ""
            reason = f"止损卖出 | 盈亏: {sign}{pnl:.2%}"
            self._log(data, f"🔴 {stock[:6]} {reason}  当前价: {price}")
            return generate_signal(data, stock, price, 1.0, "sell", reason)
        return []

    def _check_stop_profit(
        self, data: Dict, stock: str, price: float, avg_price: float
    ) -> List[Dict]:
        """固定止盈检查：盈利超过 stop_profit 比例则全仓卖出。"""
        if self.stop_profit is None or avg_price <= 0:
            return []
        pnl = (price - avg_price) / avg_price
        if pnl >= self.stop_profit:
            reason = f"止盈卖出 | 盈亏: +{pnl:.2%}"
            self._log(data, f"🟢 {stock[:6]} {reason}  当前价: {price}")
            return generate_signal(data, stock, price, 1.0, "sell", reason)
        return []

    def _check_trailing_stop(
        self, data: Dict, stock: str, price: float
    ) -> List[Dict]:
        """追踪止损检查：从持仓期最高价回撤超过 trailing_stop 比例则全仓卖出。"""
        if self.trailing_stop is None:
            return []
        # 更新历史最高价（只升不降）
        prev_high = self._trailing_high.get(stock, price)
        high = max(prev_high, price)
        self._trailing_high[stock] = high

        if high <= 0:
            return []
        drawdown = (price - high) / high
        if drawdown <= -self.trailing_stop:
            reason = (
                f"追踪止损卖出 | 当前价: {price:.2f} "
                f"最高价: {high:.2f} "
                f"回撤: {drawdown:.2%}"
            )
            self._log(data, f"🔴 {stock[:6]} {reason}")
            return generate_signal(data, stock, price, 1.0, "sell", reason)
        return []

    def _check_trailing_profit(
        self, data: Dict, stock: str, price: float, avg_price: float
    ) -> List[Dict]:
        """移动止盈检查：盈利达到激活阈值后追踪，从盈利高点回落超过回撤比例则全仓卖出。"""
        if self.trailing_profit_activate is None or self.trailing_profit_callback is None:
            return []
        if avg_price <= 0:
            return []

        pnl = (price - avg_price) / avg_price
        activated = self._tp_activated.get(stock, False)

        if not activated:
            # 未激活：判断是否达到激活阈值
            if pnl >= self.trailing_profit_activate:
                self._tp_activated[stock] = True
                self._tp_high[stock] = price
                self._log(
                    data,
                    f"🟡 {stock[:6]} 移动止盈已激活 | 盈利: +{pnl:.2%}  盈利高点: {price:.2f}",
                )
            return []

        # 已激活：更新盈利最高价（只升不降）
        prev_tp_high = self._tp_high.get(stock) or price
        tp_high = max(prev_tp_high, price)
        self._tp_high[stock] = tp_high

        if tp_high <= 0:
            return []
        callback = (price - tp_high) / tp_high
        if callback <= -self.trailing_profit_callback:
            reason = (
                f"移动止盈卖出 | 当前价: {price:.2f} "
                f"盈利高点: {tp_high:.2f} "
                f"回撤: {callback:.2%}"
            )
            self._log(data, f"🟢 {stock[:6]} {reason}")
            return generate_signal(data, stock, price, 1.0, "sell", reason)
        return []

    def _check_time_stop(
        self, data: Dict, stock: str, price: float, avg_price: float, current_date: str
    ) -> List[Dict]:
        """时间止损检查：持仓超过 time_stop_days 个自然日且未盈利则全仓卖出。"""
        if self.time_stop_days is None or avg_price <= 0:
            return []
        entry = self._entry_date.get(stock)
        if not entry:
            return []

        try:
            entry_obj = datetime.strptime(entry, "%Y%m%d")
            cur_obj = datetime.strptime(current_date, "%Y%m%d")
            days_held = (cur_obj - entry_obj).days
        except Exception:
            return []

        pnl = (price - avg_price) / avg_price
        if days_held >= self.time_stop_days and pnl <= 0:
            reason = f"时间止损卖出 | 持仓天数: {days_held}"
            self._log(data, f"🔴 {stock[:6]} {reason}  盈亏: {pnl:.2%}")
            return generate_signal(data, stock, price, 1.0, "sell", reason)
        return []

    # ──────────────────────────────────────────────────────────────────
    # 公开：主入口
    # ──────────────────────────────────────────────────────────────────

    def check(self, data: Dict) -> List[Dict]:
        """检查所有持仓的止损止盈条件，返回需要执行的卖出信号列表。

        检查优先级：
          组合粒度（任一触发则全部清仓并直接返回）：
            组合止损 → 组合追踪止损 → 组合止盈
          标的粒度（同一只股票同一 bar 只触发一次）：
            固定止损 → 追踪止损 → 固定止盈 → 移动止盈 → 时间止损

        Args:
            data: 策略 on_bar 接收的数据字典

        Returns:
            List[Dict]: 卖出信号列表，可直接 extend 到策略的 signals 中
        """
        signals: List[Dict] = []

        # 获取当前持仓
        positions: Dict = data.get("__positions__", {})
        if not positions:
            return signals

        # 获取当前 bar 日期（"YYYYMMDD" 格式）
        current_time = data.get("__current_time__", {})
        ts = current_time.get("timestamp", 0)
        try:
            current_date = datetime.fromtimestamp(ts / 1000).strftime("%Y%m%d") if ts else ""
        except Exception:
            current_date = ""

        # ── Step 1：同步标的粒度内部状态（新增/清仓自动处理）──────────
        self._sync_state(positions, current_date)

        # ── Step 2：检测是否发生了交易 ────────────────────────────────
        trade_happened = self._detect_trade(positions)

        # ── Step 3：计算当前组合净值 ──────────────────────────────────
        current_portfolio_value = self._calc_portfolio_value(data, positions)

        # ── Step 4：更新组合粒度状态（基准/最高/初始净值）────────────
        self._update_portfolio_state(current_portfolio_value, trade_happened)

        # ── Step 5：组合粒度检查（任一触发则全部清仓并直接返回）──────
        if current_portfolio_value > 0:
            # 5a. 组合止损
            portfolio_signals = self._check_portfolio_stop_loss(
                data, positions, current_portfolio_value
            )
            if portfolio_signals:
                return portfolio_signals

            # 5b. 组合追踪止损
            portfolio_signals = self._check_portfolio_trailing_stop(
                data, positions, current_portfolio_value
            )
            if portfolio_signals:
                return portfolio_signals

            # 5c. 组合止盈
            portfolio_signals = self._check_portfolio_stop_profit(
                data, positions, current_portfolio_value
            )
            if portfolio_signals:
                return portfolio_signals

        # ── Step 6：标的粒度检查 ──────────────────────────────────────
        # 延迟导入，避免与 quant_import 循环依赖
        from utils.quant_import import get_price as _get_price  # noqa: PLC0415

        for stock, pos_info in positions.items():
            avg_price: float = pos_info.get("avg_price", 0.0)

            # 获取当前价格
            price: float = _get_price(data, stock, self.price_field)
            if price <= 0:
                continue

            triggered: List[Dict] = []

            # 1. 固定止损（最高优先级）
            if not triggered:
                triggered = self._check_stop_loss(data, stock, price, avg_price)

            # 2. 追踪止损
            if not triggered:
                triggered = self._check_trailing_stop(data, stock, price)

            # 3. 固定止盈
            if not triggered:
                triggered = self._check_stop_profit(data, stock, price, avg_price)

            # 4. 移动止盈
            if not triggered:
                triggered = self._check_trailing_profit(data, stock, price, avg_price)

            # 5. 时间止损（最低优先级）
            if not triggered:
                triggered = self._check_time_stop(data, stock, price, avg_price, current_date)

            if triggered:
                # 触发止损/止盈后立即清除该股票的内部状态，
                # 防止框架尚未更新持仓时下一 bar 重复触发
                self._trailing_high.pop(stock, None)
                self._entry_date.pop(stock, None)
                self._tp_activated.pop(stock, None)
                self._tp_high.pop(stock, None)

            signals.extend(triggered)

        return signals


# ──────────────────────────────────────────────────────────────────────────────
# BarFrequencyAdapter：驱动周期适配器
# ──────────────────────────────────────────────────────────────────────────────

class BarFrequencyAdapter:
    """驱动周期适配器：将高频驱动（1m/5m）适配为低频业务节奏（daily/weekly）。

    解决的核心问题
    ──────────────
    策略逻辑对驱动周期的依赖程度不同，分为两类：

    - **类型 A（周期透明型）**：如 StopLossManager，每次 on_bar 都执行，
      驱动越细检查越频繁，天然适配任何周期，无需适配器。

    - **类型 B（周期锁定型）**：如调仓/选股逻辑，有自己固有的业务节奏
      （每日/每周），内部数据拉取周期也独立于驱动周期。
      当框架驱动是 1m 时，每分钟都会触发 on_bar，但调仓逻辑不应每分钟执行。
      适配器负责判断"当前 bar 是否满足业务触发条件"，屏蔽底层驱动差异。

    典型用法
    ────────
    ::

        # init() 中初始化一次
        def init(stocks=None, data=None):
            global freq_adapter
            freq_adapter = BarFrequencyAdapter(daily_trigger_time="09:31:00")

        # on_bar() 中使用
        def on_bar(data: Dict) -> List[Dict]:
            signals = []

            # 类型 A：每次 bar 都执行（周期透明）
            signals.extend(stop_manager.check(data))

            # 类型 B：通过适配器判断是否到了"周级别换仓时机"（周期锁定）
            if freq_adapter.is_weekly_first_day(data):
                signals.extend(_do_rebalance(data))

            return signals

    参数说明
    ────────
    Args:
        daily_trigger_time: 每日业务触发时间点（仅在分钟驱动时有意义），
                            格式 "HH:MM:SS"，默认 "09:31:00"（开盘后第一根分钟K线）。
                            日线驱动时此参数无效，每个 bar 都视为"日触发"。
    """

    def __init__(self, daily_trigger_time: str = "09:31:00"):
        self._daily_trigger_time = daily_trigger_time
        # 记录已触发"日级别"的日期，防止同日重复触发
        self._last_daily_triggered_date: Optional[str] = None
        # 记录已触发"周级别"的周标识，防止同周重复触发 "YYYY-WNN"
        self._last_weekly_triggered_key: Optional[str] = None
        # N日计数器（供 is_nth_day 使用）
        self._nth_day_counter: int = 0
        self._nth_day_last_dn: Optional[str] = None

    # ──────────────────────────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────────────────────────

    def _get_drive_period(self, data: Dict) -> str:
        """从框架上下文获取当前驱动周期，如 '1d'、'1m'、'5m'。"""
        try:
            fw = data.get("__framework__")
            if fw is not None and hasattr(fw, "config"):
                return fw.config.kline_period or "1d"
        except Exception:
            pass
        return "1d"

    def _get_date_str(self, data: Dict) -> str:
        """获取当前 bar 日期，格式 'YYYYMMDD'。"""
        current_time = data.get("__current_time__", {})
        ts = current_time.get("timestamp", 0)
        if ts:
            try:
                return datetime.fromtimestamp(ts / 1000).strftime("%Y%m%d")
            except Exception:
                pass
        return ""

    def _get_time_str(self, data: Dict) -> str:
        """获取当前 bar 时间，格式 'HH:MM:SS'。"""
        current_time = data.get("__current_time__", {})
        ts = current_time.get("timestamp", 0)
        if ts:
            try:
                return datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
            except Exception:
                pass
        return ""

    @staticmethod
    def _is_first_trade_day_of_week(dn: str) -> bool:
        """判断给定日期是否为本周第一个交易日。

        判断逻辑：
        - 周一（weekday=0）直接返回 True
        - 非周一：向前追溯最近一个工作日，若该工作日不是交易日，则当天是本周第一个交易日
        """
        from utils.stock_utils import is_trade_day as _is_trade_day  # noqa: PLC0415
        try:
            date_obj = datetime.strptime(dn, "%Y%m%d")
            if date_obj.weekday() == 0:
                return True
            prev_day = date_obj - timedelta(days=1)
            while prev_day.weekday() >= 5:  # 跳过周末
                prev_day -= timedelta(days=1)
            return not _is_trade_day(prev_day.strftime("%Y-%m-%d"))
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────
    # 公开接口
    # ──────────────────────────────────────────────────────────────────

    def is_daily_open(self, data: Dict) -> bool:
        """判断当前 bar 是否为"日级别开盘触发点"。

        触发规则（按驱动周期自动适配）：

        - **1d 驱动**：每个 bar 都触发（每天一次）
        - **1m / 5m 等分钟驱动**：当天第一次到达 ``daily_trigger_time`` 时触发一次，
          同一天后续的 bar 不再触发

        同一天只触发一次（内部用日期去重）。

        Args:
            data: 策略 on_bar 接收的数据字典

        Returns:
            bool: True 表示当前 bar 是日级别触发点
        """
        dn = self._get_date_str(data)
        if not dn:
            return False

        # 同日已触发，直接跳过
        if self._last_daily_triggered_date == dn:
            return False

        period = self._get_drive_period(data)

        if period == "1d":
            # 日线驱动：每个 bar 直接触发
            self._last_daily_triggered_date = dn
            return True

        # 分钟驱动：到达指定时间点才触发
        time_str = self._get_time_str(data)
        if time_str and time_str >= self._daily_trigger_time:
            self._last_daily_triggered_date = dn
            return True

        return False

    def is_weekly_first_day(self, data: Dict) -> bool:
        """判断当前 bar 是否为"周级别首次触发点"（本周第一个交易日的日触发点）。

        内部先调用 :meth:`is_daily_open` 确认是日触发点，
        再判断是否为本周第一个交易日，并用周标识去重防止重复触发。

        Args:
            data: 策略 on_bar 接收的数据字典

        Returns:
            bool: True 表示当前 bar 是周级别触发点
        """
        if not self.is_daily_open(data):
            return False

        dn = self._last_daily_triggered_date  # is_daily_open 已更新
        if not dn:
            return False

        if not self._is_first_trade_day_of_week(dn):
            return False

        # 用年份+周数去重，防止同一周重复触发
        try:
            date_obj = datetime.strptime(dn, "%Y%m%d")
            week_key = f"{date_obj.year}-W{date_obj.isocalendar()[1]:02d}"
        except Exception:
            return False

        if self._last_weekly_triggered_key == week_key:
            return False

        self._last_weekly_triggered_key = week_key
        return True

    def is_nth_day(self, data: Dict, n: int) -> bool:
        """判断当前 bar 是否为"每 N 个交易日触发一次"的触发点。

        从策略启动后第一个日触发点开始计数，每满 N 个交易日触发一次。
        适用于"每3日调仓"、"每5日调仓"等固定间隔换仓策略。

        Args:
            data: 策略 on_bar 接收的数据字典
            n:    触发间隔（交易日数），如 5 表示每5个交易日触发一次

        Returns:
            bool: True 表示当前 bar 是 N 日触发点
        """
        if not self.is_daily_open(data):
            return False

        dn = self._last_daily_triggered_date
        if not dn:
            return False

        # 防止同日重复计数（is_daily_open 已保证同日只进一次，此处双保险）
        if self._nth_day_last_dn == dn:
            return False

        self._nth_day_counter += 1
        self._nth_day_last_dn = dn

        return self._nth_day_counter % n == 0