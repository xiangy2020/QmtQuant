# coding: utf-8
"""
framework/core.py
量化交易框架核心 —— MyTraderCallback（交易回调）和 QuantFramework（主类）。
"""
import time
import datetime
import traceback
import importlib.util
from typing import Dict, List, Optional, Union, Any
import logging
import sys
import shutil
from types import SimpleNamespace
import threading

from env import IS_REMOTE, IS_WINDOWS, xtdata

if IS_REMOTE:
    import os
    _xqshare_src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xqshare")
    if _xqshare_src not in sys.path:
        sys.path.insert(0, _xqshare_src)
    from xqshare import connect as _xqshare_connect
    _xqshare_connect()
    class XtQuantTrader:
        pass
    class StockAccount:
        def __init__(self, account_id, account_type="STOCK"):
            self.account_id = account_id
            self.account_type = account_type
    class XtQuantTraderCallback:
        pass
    class _XtConstantProxy:
        SECURITY_ACCOUNT = 2
        STOCK_BUY = 23
        STOCK_SELL = 24
        FIX_PRICE = 11
        ORDER_SUCCEEDED = 56
        DIRECTION_FLAG_LONG = 48
        OFFSET_FLAG_OPEN = 48
        OFFSET_FLAG_CLOSE = 49
        def __getattr__(self, name):
            return 0
    xtconstant = _XtConstantProxy()
else:
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    from xtquant.xttype import StockAccount
    from xtquant import xtconstant

from framework.trade import TradeManager
from framework.risk import RiskManager
from utils import QuTools, determine_pool_type, format_price, round_price, get_price_decimals, check_t0_support, get_t0_details
from framework.config import Config

import numpy as np
import pandas as pd
import os
import holidays

from framework.callbacks import FrameworkCallbacks, DefaultCallbacks
from framework.triggers import TriggerFactory
from framework.stock_filter import StockFilter, StaticStockFilter
from framework.backtest import BacktestMixin
from framework.lifecycle import LifecycleMixin
from framework.live import LiveMixin


class MyTraderCallback(XtQuantTraderCallback):
    def __init__(self, callbacks: FrameworkCallbacks):
        super().__init__()
        self.callbacks = callbacks
        self.price_decimals = 2  # 默认价格精度，会在回测开始时根据股票池类型更新
        self.callbacks.on_log("交易回调已初始化", "INFO")

    def set_price_decimals(self, decimals: int):
        """设置价格精度"""
        self.price_decimals = decimals

    def on_stock_order(self, order):
        """委托回报推送"""
        try:
            direction_map = {
                xtconstant.STOCK_BUY: '买入',
                xtconstant.STOCK_SELL: '卖出'
            }
            status_map = {
                0: '已提交', 1: '已接受', 2: '已拒绝',
                3: '已撤销', 4: '已成交', 5: '部分成交'
            }
            formatted_time = "未知"
            order_time_val = getattr(order, 'order_time', None)
            if order_time_val:
                try:
                    timestamp = float(order_time_val)
                    if timestamp > 1e10:
                        timestamp = timestamp / 1000
                    formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        formatted_time = datetime.datetime.strptime(str(order_time_val), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        formatted_time = str(order_time_val)
                except Exception as e:
                    formatted_time = f"时间转换错误: {e}"

            decimals = self.price_decimals
            order_msg = (
                f"委托信息 - "
                f"时间: {formatted_time} | "
                f"股票代码: {order.stock_code} | "
                f"方向: {direction_map.get(order.order_type, '未知')} | "
                f"委托价格: {order.price:.{decimals}f} | "
                f"数量: {order.order_volume} | "
                f"委托编号: {order.order_id} | "
                f"原因: {order.status_msg or '策略交易'}"
            )
            self.callbacks.on_log(order_msg, "TRADE")
        except Exception as e:
            self.callbacks.on_log(f"处理委托回报时出错: {str(e)}", "ERROR")

    def on_stock_trade(self, trade):
        """成交回报推送"""
        try:
            direction_map = {
                xtconstant.STOCK_BUY: '买入',
                xtconstant.STOCK_SELL: '卖出'
            }
            actual_price = getattr(trade, 'actual_price', trade.traded_price)
            formatted_time = "未知"
            traded_time_val = getattr(trade, 'traded_time', None)
            if traded_time_val:
                try:
                    timestamp = float(traded_time_val)
                    if timestamp > 1e10:
                        timestamp = timestamp / 1000
                    formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        formatted_time = datetime.datetime.strptime(str(traded_time_val), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        formatted_time = str(traded_time_val)
                except Exception as e:
                    formatted_time = f"时间转换错误: {e}"

            decimals = self.price_decimals
            trade_msg = (
                f"成交信息 - "
                f"时间: {formatted_time} | "
                f"股票代码: {trade.stock_code} | "
                f"方向: {direction_map.get(trade.order_type, '未知')} | "
                f"实际成交价: {actual_price:.{decimals}f} | "
                f"成交数量: {trade.traded_volume} | "
                f"成交金额: {trade.traded_amount:.{decimals}f} | "
                f"成交编号: {trade.traded_id} | "
                f"原因: {trade.order_remark or '策略交易'}"
            )
            self.callbacks.on_log(trade_msg, "TRADE")
        except Exception as e:
            self.callbacks.on_log(f"处理成交回报时出错: {str(e)}", "ERROR")

    def on_order_error(self, order_error):
        """委托错误回报推送"""
        try:
            error_msg = (
                f"委托错误 - "
                f"股票代码: {order_error.stock_code} | "
                f"错误代码: {order_error.error_id} | "
                f"错误信息: {order_error.error_msg} | "
                f"备注: {order_error.order_remark}"
            )
            self.callbacks.on_log(error_msg, "ERROR")
        except Exception as e:
            self.callbacks.on_log(f"处理委托错误时出错: {str(e)}", "ERROR")

    def on_cancel_error(self, cancel_error):
        """撤单错误回报推送"""
        try:
            error_msg = (
                f"撤单错误 - "
                f"委托编号: {cancel_error.order_id} | "
                f"错误代码: {cancel_error.error_id} | "
                f"错误信息: {cancel_error.error_msg}"
            )
            self.callbacks.on_log(error_msg, "ERROR")
        except Exception as e:
            self.callbacks.on_log(f"处理撤单错误时出错: {str(e)}", "ERROR")

    def on_disconnected(self):
        """连接断开"""
        self.callbacks.on_log("交易连接已断开", "WARNING")

    def on_order_stock_async_response(self, response):
        """异步下单回报推送"""
        try:
            msg = f"异步委托回调 - 备注: {response.order_remark}"
            self.callbacks.on_log(msg, "TRADE")
        except Exception as e:
            self.callbacks.on_log(f"处理异步下单回报时出错: {str(e)}", "ERROR")

    def on_cancel_order_stock_async_response(self, response):
        """撤单异步回报推送"""
        try:
            msg = f"撤单异步回报 - 委托编号: {response.order_id}"
            self.callbacks.on_log(msg, "TRADE")
        except Exception as e:
            self.callbacks.on_log(f"处理撤单异步回报时出错: {str(e)}", "ERROR")

    def on_account_status(self, status):
        """账户状态变动推送"""
        try:
            msg = f"账户状态变动 - 账户: {status.account_id} | 状态: {status.status}"
            self.callbacks.on_log(msg, "INFO")
        except Exception as e:
            self.callbacks.on_log(f"处理账户状态变动时出错: {str(e)}", "ERROR")

    def on_stock_position(self, position):
        """持仓变动推送"""
        try:
            decimals = self.price_decimals
            msg = (
                f"持仓变动 - "
                f"股票代码: {position.stock_code} | "
                f"持仓数量: {position.volume} | "
                f"最新价格: {getattr(position, 'current_price', 0):.{decimals}f} | "
                f"持仓市值: {getattr(position, 'market_value', 0):.{decimals}f} | "
                f"持仓盈亏: {getattr(position, 'profit', 0):.{decimals}f}"
            )
            self.callbacks.on_log(msg, "INFO")
        except Exception as e:
            self.callbacks.on_log(f"处理持仓变动时出错: {str(e)}", "ERROR")

    def on_connected(self):
        """连接成功推送"""
        self.callbacks.on_log("交易连接成功", "INFO")

    def on_stock_asset(self, asset):
        """资金变动推送"""
        pass


class QuantFramework(BacktestMixin, LifecycleMixin, LiveMixin):
    """量化交易框架主类"""

    def __init__(self, config_path: str, strategy_file: str,
                 callbacks: FrameworkCallbacks = None):
        """初始化框架

        Args:
            config_path:  配置文件路径
            strategy_file: 策略文件路径
callbacks:    框架回调协议实现（CLI/测试各自提供适配器）
        """
        self.config_path = config_path
        self.config = Config(config_path)
        self.is_running = False

        # 初始化 QMT 客户端路径，优先使用 system.userdata_path
        self.qmt_path = self.config.config_dict.get("system", {}).get("userdata_path", "")
        if not self.qmt_path:
            self.qmt_path = self.config.config_dict.get("qmt", {}).get("path", "")

        self.account = None
        self.trader = None
        self.callback = None
        self.strategy_module = None
        self.backtest_records = {}
        self.daily_price_cache = {}
        self._cached_benchmark_close = {}

        # T+0 交易模式标识（默认关闭，在 run() 中根据股票池判断）
        self.t0_mode = False

        # 运行时间记录
        self.start_time = None
        self.end_time = None
        self.total_runtime = 0

        # 初始化回调协议（未传入时使用默认实现，打印到 stdout）
        self.callbacks: FrameworkCallbacks = callbacks if callbacks is not None else DefaultCallbacks()

        # 加载策略模块
        try:
            self.strategy_module = self.load_strategy(strategy_file)
        except Exception as e:
            self.callbacks.on_log(f"策略模块加载失败: {str(e)}", "ERROR")
            traceback.print_exc()
            raise

        # 当前运行模式
        self.run_mode = self.config.run_mode

        # 创建触发器
        self.trigger = TriggerFactory.create_trigger(self, self.config.config_dict)

        # 创建股票过滤器：若配置中有 data.stock_list，自动包装为 StaticStockFilter
        raw_stock_list = self.config.get_stock_list()
        self.stock_filter: StockFilter = StaticStockFilter(raw_stock_list)

        # 初始化各模块（TradeManager 传入 self 供内部使用）
        self.trade_mgr = TradeManager(self.config, self)
        self.risk_mgr = RiskManager(self.config)
        self.tools = QuTools()

        # 清除可能存在的历史数据缓存
        for attr in ('historical_data_ref', 'time_field_cache', 'time_idx_cache'):
            if hasattr(self, attr):
                delattr(self, attr)

    # ------------------------------------------------------------------ #
    # 日志 / 工具方法                                                      #
    # ------------------------------------------------------------------ #

    def _log(self, message, level="INFO"):
        """统一日志入口，通过 FrameworkCallbacks 协议输出"""
        self.callbacks.on_log(message, level)

    def _should_log(self):
        """检查是否应该输出日志（保持兼容性）"""
        return True

    def _cache_should_log(self):
        """在回测开始时缓存日志开关状态（保持兼容性）"""
        pass

    # ------------------------------------------------------------------ #
    # 策略加载                                                             #
    # ------------------------------------------------------------------ #

    def load_strategy(self, strategy_file: str):
        """动态加载策略模块

        Args:
            strategy_file: 策略文件路径

        Returns:
            module: 策略模块
        """
        import importlib.util
        import sys
        import os

        strategy_file = os.path.abspath(strategy_file)
        module_name = os.path.splitext(os.path.basename(strategy_file))[0]

        spec = importlib.util.spec_from_file_location(module_name, strategy_file)
        strategy_module = importlib.util.module_from_spec(spec)

        # 注册到 sys.modules，让 VSCode 断点生效
        sys.modules[module_name] = strategy_module
        strategy_module.__file__ = strategy_file

        spec.loader.exec_module(strategy_module)
        return strategy_module

    # ------------------------------------------------------------------ #
    # 账户初始化                                                           #
    # ------------------------------------------------------------------ #

    def init_trader_and_account(self):
        """初始化交易接口和账户"""
        if self.run_mode == 'live':
            self._init_real_account()
        else:
            self._init_virtual_account()

    def _init_virtual_account(self):
        """初始化虚拟账户"""
        self.account = StockAccount(
            self.config.account_id,
            self.config.account_type
        )

        self.benchmark = self.config.benchmark
        self.config.config_dict["backtest"]["benchmark"] = self.benchmark

        init_capital = self.config.config_dict["backtest"]["init_capital"]

        self.trade_mgr.assets = {
            "account_type": xtconstant.SECURITY_ACCOUNT,
            "account_id": self.config.account_id,
            "cash": init_capital,
            "frozen_cash": 0.0,
            "market_value": 0.0,
            "total_asset": init_capital,
            "benchmark": self.benchmark
        }
        self.trade_mgr.positions = {}
        self.trade_mgr.orders = {}
        self.trade_mgr.trades = {}

        self._log(f"虚拟账户初始化完成: {self.config.account_id}")
        self._log(f"初始资产: {self.trade_mgr.assets}")
        self._log(f"基准合约: {self.benchmark}")

    def create_callback(self) -> XtQuantTraderCallback:
        """创建交易回调对象"""
        return MyTraderCallback(self.callbacks)

    # ------------------------------------------------------------------ #
    # 数据初始化                                                           #
    # ------------------------------------------------------------------ #

    def init_data(self):
        """初始化行情数据（下载历史数据到 miniQMT）"""
        download_complete = False

        def download_progress(progress):
            nonlocal download_complete
            self.callbacks.on_log(f"下载进度: {progress}", "INFO")
            if progress['finished'] >= progress['total']:
                download_complete = True

        stock_codes = self.get_stock_list()

        if not stock_codes:
            self.callbacks.on_log("警告: 股票池为空，无法下载历史数据", "WARNING")
            return

        self.callbacks.on_log(f"开始下载{len(stock_codes)}只股票的历史数据...", "INFO")

        xtdata.download_history_data2(
            stock_codes,
            period=self.config.kline_period,
            start_time=self.config.backtest_start,
            end_time=self.config.backtest_end,
            incrementally=True,
            callback=download_progress
        )

        while not download_complete:
            time.sleep(1)

    # ------------------------------------------------------------------ #
    # 行情回调                                                             #
    # ------------------------------------------------------------------ #

    def on_quote_callback(self, data: Dict):
        """行情数据回调处理"""
        try:
            timestamp = data.get("timestamp", int(time.time()))
            if isinstance(timestamp, str):
                try:
                    timestamp = int(timestamp)
                except Exception:
                    timestamp = int(time.time())

            if timestamp > 1e10:
                dt = datetime.datetime.fromtimestamp(timestamp / 1000)
            else:
                dt = datetime.datetime.fromtimestamp(timestamp)

            time_info = {
                "timestamp": timestamp,
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M:%S")
            }

            if not self.tools.is_trade_day(time_info["date"]):
                self.callbacks.on_log(f"日期 {time_info['date']} 不是交易日，跳过策略执行", "INFO")
                return

            data_with_time = {"__current_time__": time_info}
            for key, value in data.items():
                if key != "__current_time__":
                    data_with_time[key] = value

            if not self.trigger.should_trigger(timestamp, data_with_time):
                trigger_type = self.config.config_dict.get("backtest", {}).get("trigger", {}).get("type", "tick")
                if trigger_type in ("1m", "5m"):
                    current_time_str = time_info["time"]
                    dt_time = datetime.datetime.strptime(current_time_str, "%H:%M:%S")
                    if trigger_type == "1m" and dt_time.second >= 57:
                        pass
                    elif trigger_type == "5m" and dt_time.minute % 5 == 4 and dt_time.second >= 57:
                        pass
                    else:
                        return
                else:
                    return

            if not self.risk_mgr.check_risk(data_with_time):
                return

            current_time = datetime.datetime.fromtimestamp(timestamp)
            data_with_time["__current_time__"] = {
                "timestamp": timestamp,
                "datetime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "date": current_time.strftime("%Y-%m-%d"),
                "time": current_time.strftime("%H:%M:%S")
            }

            if hasattr(self, 'trade_mgr') and self.trade_mgr:
                data_with_time["__account__"] = self.trade_mgr.assets
                data_with_time["__positions__"] = self.trade_mgr.positions
                data_with_time["__stock_list__"] = self.get_stock_list()
                data_with_time["__framework__"] = self

            # 检查股票数据是否为空
            stock_data_empty = True
            empty_stocks = []
            for key, value in data_with_time.items():
                if key.startswith("__"):
                    continue
                if isinstance(value, pd.Series) and not value.empty:
                    stock_data_empty = False
                elif isinstance(value, pd.Series) and value.empty:
                    empty_stocks.append(key)
                elif not value:
                    empty_stocks.append(key)

            if stock_data_empty:
                current_time_str = data_with_time.get("__current_time__", {}).get("datetime", "未知时间")
                self.callbacks.on_log(
                    f"警告: 时间点 {current_time_str} 的所有股票数据为空，跳过策略调用", "WARNING"
                )
                if empty_stocks:
                    self.callbacks.on_log(
                        f"空数据股票列表: {', '.join(empty_stocks[:10])}"
                        + (f" 等{len(empty_stocks)}只股票" if len(empty_stocks) > 10 else ""),
                        "WARNING"
                    )
                return

            if empty_stocks:
                current_time_str = data_with_time.get("__current_time__", {}).get("datetime", "未知时间")
                self.callbacks.on_log(
                    f"警告: 时间点 {current_time_str} 有 {len(empty_stocks)} 只股票数据为空: {', '.join(empty_stocks[:5])}"
                    + (f" 等" if len(empty_stocks) > 5 else ""),
                    "WARNING"
                )

            signals = self.strategy_module.on_bar(data_with_time)

            if signals:
                for signal in signals:
                    if 'price' in signal:
                        signal['price'] = round(float(signal['price']), self.price_decimals)
                self.trade_mgr.process_signals(signals)

        except Exception as e:
            self.log_error(f"行情处理异常: {str(e)}")
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # 主入口                                                               #
    # ------------------------------------------------------------------ #

    def run(self, init_data_enabled: bool = False, risk_free_rate: float = None):
        """启动框架

        Args:
            init_data_enabled: 是否初始化行情数据（下载历史数据到 miniQMT）。
CLI 层从 --init-data 参数传入。
                               默认 False（不下载）。
            risk_free_rate:    无风险利率（小数形式，如 0.03 表示 3%），用于计算夏普/索提诺等指标。
                               优先级：参数传入 > .qmt 配置文件 backtest.risk_free_rate > 默认值 0.03。
        """
        self.start_time = time.time()
        start_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.callbacks.on_log(f"策略开始运行时间: {start_datetime}", "INFO")
        self.callbacks.on_log("开始初始化交易接口和数据...", "INFO")

        # 解析无风险利率
        if risk_free_rate is not None:
            self._risk_free_rate = float(risk_free_rate)
        else:
            cfg_rfr = self.config.config_dict.get("backtest", {}).get("risk_free_rate", None)
            self._risk_free_rate = float(cfg_rfr) if cfg_rfr is not None else 0.03
        self.callbacks.on_log(f"无风险利率: {self._risk_free_rate:.4f} ({self._risk_free_rate*100:.2f}%)", "INFO")

        try:
            init_start = time.time()
            self.init_trader_and_account()
            self.callbacks.on_log(f"交易接口初始化耗时: {time.time() - init_start:.2f}秒", "INFO")

            self.daily_price_cache = {}
            self._cached_benchmark_close = {}

            self.callbacks.on_log(f"数据初始化设置: {'启用' if init_data_enabled else '禁用'}", "INFO")

            if init_data_enabled:
                data_init_start = time.time()
                self.callbacks.on_log("开始初始化行情数据...", "INFO")
                self.init_data()
                self.callbacks.on_log(f"数据初始化耗时: {time.time() - data_init_start:.2f}秒", "INFO")
            else:
                self.callbacks.on_log("跳过数据初始化（根据设置禁用）", "INFO")

            stock_list_start = time.time()
            stock_codes = self.get_stock_list()
            self.callbacks.on_log(f"股票列表加载耗时: {time.time() - stock_list_start:.2f}秒", "INFO")

            # 判断股票池类型并设置价格精度
            self.pool_type, self.price_decimals = determine_pool_type(stock_codes)
            self.trade_mgr.set_price_decimals(self.price_decimals)

            pool_type_names = {
                'stock_only': '纯股票', 'etf_only': '纯ETF', 'mixed': '股票+ETF混合'
            }
            self.callbacks.on_log(
                f"股票池类型: {pool_type_names.get(self.pool_type, self.pool_type)}, "
                f"价格精度: {self.price_decimals}位小数", "INFO"
            )

            # T+0 模式检验
            t0_support_type, self.t0_mode = check_t0_support(stock_codes)
            self.trade_mgr.set_t0_mode(self.t0_mode)

            if t0_support_type == 'all_t0':
                self.callbacks.on_log(
                    "T+0交易模式已启用 - 股票池中全部为T0型ETF，支持当日买入当日卖出", "INFO"
                )
            elif t0_support_type == 'mixed':
                t0_details = get_t0_details(stock_codes)
                warning_msg = (
                    f"股票池中包含混合品种：\n"
                    f"- 支持T+0的ETF: {t0_details['t0_count']}只\n"
                    f"- 不支持T+0的品种: {len(t0_details['non_t0_stocks'])}只\n\n"
                    f"系统将使用T+1模式运行。如需使用T+0模式，请确保股票池中只包含T0型ETF。"
                )
                self.callbacks.on_log(
                    f"T+0模式未启用：股票池包含{t0_details['t0_count']}只T0型ETF和{len(t0_details['non_t0_stocks'])}只非T0品种",
                    "WARNING"
                )
                self.callbacks.on_t0_warning(warning_msg)
            else:
                self.callbacks.on_log("交易模式: T+1（标准A股交易规则）", "INFO")

            # 构建初始化数据结构
            init_data = {
                "__current_time__": {
                    "timestamp": int(time.time()),
                    "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                    "time": datetime.datetime.now().strftime("%H:%M:%S")
                },
                "__account__": self.trade_mgr.assets,
                "__positions__": self.trade_mgr.positions,
                "__stock_list__": stock_codes,
                "__framework__": self
            }

            strategy_init_start = time.time()
            self.strategy_module.init(stock_codes, init_data)
            self.callbacks.on_log(f"策略初始化耗时: {time.time() - strategy_init_start:.2f}秒", "INFO")

            self.is_running = True

            preprocess_time = time.time() - self.start_time
            self.callbacks.on_log(f"预处理阶段总耗时: {preprocess_time:.2f}秒", "INFO")
            self.callbacks.on_log("开始执行策略主逻辑...", "INFO")

            strategy_start = time.time()
            if self.run_mode == 'live':
                self._run_live()
            else:
                self._run_backtest()
            self.callbacks.on_log(f"策略主逻辑执行耗时: {time.time() - strategy_start:.2f}秒", "INFO")

            while self.is_running:
                time.sleep(1)

        except Exception as e:
            error_msg = "框架运行异常: " + str(e)
            logging.error(error_msg, exc_info=True)
            self.callbacks.on_log(error_msg, "ERROR")
            raise

        finally:
            self.end_time = time.time()
            self.total_runtime = self.end_time - self.start_time
            end_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.callbacks.on_log(f"策略结束运行时间: {end_datetime}", "INFO")
            self.callbacks.on_log(f"策略总运行时长: {self.total_runtime:.2f}秒", "INFO")

            hours = int(self.total_runtime // 3600)
            minutes = int((self.total_runtime % 3600) // 60)
            seconds = self.total_runtime % 60

            if hours > 0:
                self.callbacks.on_log(f"策略运行时长: {hours}小时{minutes}分钟{seconds:.2f}秒", "INFO")
            elif minutes > 0:
                self.callbacks.on_log(f"策略运行时长: {minutes}分钟{seconds:.2f}秒", "INFO")
            else:
                self.callbacks.on_log(f"策略运行时长: {seconds:.2f}秒", "INFO")

            self.callbacks.on_finished()
            self.stop()

    # ------------------------------------------------------------------ #
    # 辅助方法                                                             #
    # ------------------------------------------------------------------ #

    def get_stock_list(self):
        """获取股票列表"""
        stock_codes = []
        try:
            stock_codes = self.config.get_stock_list()
            if stock_codes:
                self.callbacks.on_log(f"从配置文件读取到 {len(stock_codes)} 支股票", "INFO")
            else:
                stock_list_file = self.config.config_dict["data"].get("stock_list_file", "")
                if stock_list_file and os.path.exists(stock_list_file):
                    with open(stock_list_file, 'r', encoding='utf-8') as f:
                        stock_codes = [line.strip() for line in f if line.strip()]
                    self.callbacks.on_log(f"从兼容文件 {stock_list_file} 读取到 {len(stock_codes)} 支股票", "INFO")
                    self.config.update_stock_list(stock_codes)
                    self.config.save_config()
                else:
                    stock_codes = ["000001.SZ"]
                    self.callbacks.on_log("股票列表为空，使用默认股票: 000001.SZ", "WARNING")
        except Exception as e:
            stock_codes = ["000001.SZ"]
            self.callbacks.on_log(f"读取股票列表出错: {str(e)}，使用默认股票: 000001.SZ", "ERROR")
        return stock_codes

    def _check_period_consistency(self):
        """检查数据周期和触发周期的一致性"""
        try:
            data_period = self.config.kline_period
            trigger_type = self.config.config_dict.get("backtest", {}).get("trigger", {}).get("type", "tick")

            if trigger_type == "custom":
                return

            period_consistency_map = {
                "tick": "tick", "1m": "1m", "5m": "5m", "1d": "1d"
            }
            expected_data_period = period_consistency_map.get(trigger_type, "tick")

            if data_period != expected_data_period:
                trigger_type_names = {
                    "tick": "Tick触发", "1m": "1分钟K线触发",
                    "5m": "5分钟K线触发", "1d": "日K线触发"
                }
                data_period_names = {
                    "tick": "tick数据", "1m": "1分钟K线",
                    "5m": "5分钟K线", "1d": "日K线"
                }
                trigger_name = trigger_type_names.get(trigger_type, trigger_type)
                data_name = data_period_names.get(data_period, data_period)
                expected_name = data_period_names.get(expected_data_period, expected_data_period)

                message = f"""数据周期与触发类型不匹配！

当前配置：
• 数据设置周期：{data_name}
• 触发类型：{trigger_name}

建议配置：
• 数据设置周期：{expected_name}
• 触发类型：{trigger_name}

不匹配可能导致：
- 性能问题（数据精度过高或过低）
- 触发精度问题（错过关键时间点）
- 策略执行异常

是否继续运行回测？"""

                should_continue = self.callbacks.on_period_mismatch(message)

                if not should_continue:
                    self.callbacks.on_log("用户取消运行：数据周期与触发类型不匹配", "WARNING")
                    self.is_running = False
                    return
                else:
                    self.callbacks.on_log(
                        f"警告：继续运行不匹配配置 - 数据周期:{data_name}, 触发类型:{trigger_name}", "WARNING"
                    )

        except Exception as e:
            self.callbacks.on_log(f"周期一致性检查时出错: {str(e)}", "WARNING")
