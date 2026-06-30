# -*- coding: utf-8 -*-
"""
framework/live/mixin.py
实盘模式 Mixin —— _init_real_account、_run_live、实盘账户状态同步等实盘核心方法。
由 QuantFramework 通过多继承引入，不可单独实例化。
"""
import datetime
import logging
import time
import traceback
from typing import Dict, List, Optional

# 只导入平台常量，不导入 xtdata（避免模块级触发 xqshare 网络连接）
from env import IS_WINDOWS, IS_REMOTE

# xtdata 在方法内部按需获取，避免 import 时触发 xqshare.connect()
def _get_xtdata():
    from env import xtdata
    return xtdata

if IS_WINDOWS:
    from xtquant.xttrader import XtQuantTrader
    from xtquant.xttype import StockAccount
    from xtquant import xtconstant
else:
    # Mac/Linux 占位符（实盘只在 Windows 上运行，此处仅保证 import 不报错）
    class XtQuantTrader:
        pass
    class StockAccount:
        def __init__(self, account_id, account_type="STOCK"):
            self.account_id = account_id
            self.account_type = account_type
    class _XtConstantProxy:
        SECURITY_ACCOUNT = 2
        STOCK_BUY = 23
        STOCK_SELL = 24
        FIX_PRICE = 11
        ORDER_SUCCEEDED = 56
        def __getattr__(self, name):
            return 0
    xtconstant = _XtConstantProxy()

class LiveMixin:
    """实盘模式 Mixin"""

    # ------------------------------------------------------------------ #
    # 一、实盘账户初始化                                                   #
    # ------------------------------------------------------------------ #

    def _init_real_account(self):
        """初始化真实账户（实盘模式）。

        从配置文件读取 account_id / qmt_path / session_id，
        连接 QMT 客户端，查询真实资金和持仓写入 trade_mgr。
        连接失败时抛出异常终止启动。
        """
        account_id = self.config.account_id
        qmt_path = self.qmt_path
        session_id = self.config.session_id

        self._log(f"[实盘] 初始化真实账户: account_id={account_id}, qmt_path={qmt_path}, session_id={session_id}", "INFO")

        if not IS_WINDOWS:
            raise RuntimeError("实盘模式仅支持 Windows 平台（需要 xtquant）。当前平台不支持实盘运行。")

        if not qmt_path:
            raise ValueError("实盘模式需要配置 system.userdata_path（QMT 客户端路径），当前为空。")

        # 创建账户对象
        self.account = StockAccount(account_id, "STOCK")

        # 创建交易 API 并连接
        self.trader = XtQuantTrader(qmt_path, session_id)

        # 注册回调（通过 create_callback() 创建交易回调对象）
        self.trader.register_callback(self.create_callback())

        # 建立连接
        connect_result = self.trader.connect()
        if connect_result != 0:
            raise ConnectionError(f"[实盘] QMT 连接失败，返回码: {connect_result}。请检查 QMT 客户端是否已启动。")

        self._log("[实盘] QMT 连接成功", "INFO")

        # 订阅账户（必须在 connect 之后）
        self.trader.subscribe(self.account)

        # 查询真实资金
        assets = self.trader.query_stock_asset(self.account)
        if assets is None:
            raise RuntimeError("[实盘] 查询账户资金失败，请检查账户配置。")

        self.trade_mgr.assets = {
            "account_type": xtconstant.SECURITY_ACCOUNT,
            "account_id": account_id,
            "cash": float(getattr(assets, 'cash', 0)),
            "frozen_cash": float(getattr(assets, 'frozen_cash', 0)),
            "market_value": float(getattr(assets, 'market_value', 0)),
            "total_asset": float(getattr(assets, 'total_asset', 0)),
            "benchmark": self.config.config_dict.get("backtest", {}).get("benchmark", "000300.SH"),
        }
        self._log(f"[实盘] 账户资金查询成功: 可用资金={self.trade_mgr.assets['cash']:.2f}, 总资产={self.trade_mgr.assets['total_asset']:.2f}", "INFO")

        # 查询真实持仓
        positions = self.trader.query_stock_positions(self.account)
        self.trade_mgr.positions = {}
        if positions:
            for pos in positions:
                code = getattr(pos, 'stock_code', '')
                if not code:
                    continue
                self.trade_mgr.positions[code] = {
                    "account_type": xtconstant.SECURITY_ACCOUNT,
                    "account_id": account_id,
                    "stock_code": code,
                    "volume": int(getattr(pos, 'volume', 0)),
                    "can_use_volume": int(getattr(pos, 'can_use_volume', 0)),
                    "open_price": float(getattr(pos, 'open_price', 0)),
                    "market_value": float(getattr(pos, 'market_value', 0)),
                    "frozen_volume": int(getattr(pos, 'frozen_volume', 0)),
                    "on_road_volume": int(getattr(pos, 'on_road_volume', 0)),
                    "yesterday_volume": int(getattr(pos, 'yesterday_volume', 0)),
                    "avg_price": float(getattr(pos, 'avg_price', 0)),
                    "current_price": float(getattr(pos, 'current_price', 0)),
                }
        self._log(f"[实盘] 持仓查询成功: 共 {len(self.trade_mgr.positions)} 只持仓", "INFO")

        # 将 trader 传递给 trade_mgr，供 _place_order_live 使用
        self.trade_mgr.live_trader = self.trader
        self.trade_mgr.live_account = self.account

    def _create_live_callback(self):
        """创建实盘模式下的简单回调对象。"""
        framework = self

        if IS_WINDOWS:
            from xtquant.xttrader import XtQuantTraderCallback as _Base
        else:
            _Base = object

        class _SimpleLiveCallback(_Base):
            def on_stock_trade(self, trade):
                """成交回报：更新框架内存状态"""
                try:
                    framework._on_live_trade(trade)
                except Exception as e:
                    framework._log(f"[实盘] on_stock_trade 处理异常: {e}", "ERROR")

            def on_order_error(self, order_error):
                """委托错误回报"""
                try:
                    framework._on_live_order_error(order_error)
                except Exception as e:
                    framework._log(f"[实盘] on_order_error 处理异常: {e}", "ERROR")

            def on_disconnected(self):
                framework._log("[实盘] 交易连接断开！", "ERROR")

            def on_connected(self):
                framework._log("[实盘] 交易连接成功", "INFO")

        return _SimpleLiveCallback()

    # ------------------------------------------------------------------ #
    # 二、实盘行情驱动                                                     #
    # ------------------------------------------------------------------ #

    def _run_live(self):
        """实盘模式主循环。

        1. 订阅实时行情（subscribe_quote）
        2. 注册盘前/盘后定时任务（run_time）
        3. 阻塞等待行情推送（xtdata.run）
        """
        self._log("[实盘] 启动实盘行情驱动...", "INFO")

        stock_codes = self.get_stock_list()
        data_period = self.trigger.get_data_period()

        self._log(f"[实盘] 订阅 {len(stock_codes)} 只股票的 {data_period} 行情", "INFO")

        _xtdata = _get_xtdata()

        # 订阅实时行情
        _xtdata.subscribe_quote(
            stock_code=stock_codes,
            period=data_period,
            start_time='',
            end_time='',
            count=0,
            callback=self._on_live_market_data,
        )

        # 注册盘前/盘后定时任务
        market_callback_cfg = self.config.config_dict.get("market_callback", {})
        pre_market_enabled = market_callback_cfg.get("pre_market_enabled", False)
        pre_market_time = market_callback_cfg.get("pre_market_time", "09:00:00")
        post_market_enabled = market_callback_cfg.get("post_market_enabled", False)
        post_market_time = market_callback_cfg.get("post_market_time", "15:30:00")

        if pre_market_enabled and hasattr(self.strategy_module, 'on_pre_market'):
            _xtdata.run_time(
                func=self._on_live_pre_market,
                intervalType='1nDay',
                timeString=pre_market_time,
            )
            self._log(f"[实盘] 已注册盘前定时任务，触发时间: {pre_market_time}", "INFO")

        if post_market_enabled and hasattr(self.strategy_module, 'on_post_market'):
            _xtdata.run_time(
                func=self._on_live_post_market,
                intervalType='1nDay',
                timeString=post_market_time,
            )
            self._log(f"[实盘] 已注册盘后定时任务，触发时间: {post_market_time}", "INFO")

        self._log("[实盘] 开始阻塞等待行情推送...", "INFO")
        _xtdata.run()

    def _on_live_market_data(self, data: Dict):
        """实盘行情推送回调。

        过滤 QMT 启动时回放的历史 bar，构建 context 后调用 on_bar。
        """
        try:
            # 解析 bar 时间
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            bar_date = self._extract_bar_date(data)

            # 过滤历史 bar（QMT 启动时会回放当日历史 bar）
            if bar_date and bar_date != today_str:
                return

            # 刷新账户状态（每 bar 触发前同步真实持仓/资金）
            self._refresh_live_account()

            # 构建 context
            context = self._build_live_context(data)

            # 调用策略主逻辑
            signals = self.strategy_module.on_bar(context)

            # 处理信号
            if signals:
                for signal in signals:
                    if 'price' in signal:
                        signal['price'] = round(float(signal['price']), self.price_decimals)
                self.trade_mgr.process_signals(signals)

        except Exception as e:
            self._log(f"[实盘] 行情回调处理异常: {e}\n{traceback.format_exc()}", "ERROR")

    def _on_live_pre_market(self):
        """实盘盘前定时回调"""
        try:
            self._log(f"[实盘] 执行盘前回调 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
            self._refresh_live_account()
            context = self._build_live_context({})
            signals = self.strategy_module.on_pre_market(context)
            if signals:
                for signal in signals:
                    if 'price' in signal:
                        signal['price'] = round(float(signal['price']), self.price_decimals)
                self.trade_mgr.process_signals(signals)
        except Exception as e:
            self._log(f"[实盘] 盘前回调异常: {e}\n{traceback.format_exc()}", "ERROR")

    def _on_live_post_market(self):
        """实盘盘后定时回调"""
        try:
            self._log(f"[实盘] 执行盘后回调 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
            self._refresh_live_account()
            context = self._build_live_context({})
            signals = self.strategy_module.on_post_market(context)
            if signals:
                for signal in signals:
                    if 'price' in signal:
                        signal['price'] = round(float(signal['price']), self.price_decimals)
                self.trade_mgr.process_signals(signals)
        except Exception as e:
            self._log(f"[实盘] 盘后回调异常: {e}\n{traceback.format_exc()}", "ERROR")

    # ------------------------------------------------------------------ #
    # 三、实盘账户状态同步                                                 #
    # ------------------------------------------------------------------ #

    def _refresh_live_account(self):
        """每 bar 触发前刷新真实持仓和资金。

        查询失败时使用上一次缓存值并记录警告日志。
        """
        if not IS_WINDOWS or not hasattr(self, 'trader') or self.trader is None:
            return

        try:
            # 刷新资金
            assets = self.trader.query_stock_asset(self.account)
            if assets is not None:
                self.trade_mgr.assets.update({
                    "cash": float(getattr(assets, 'cash', self.trade_mgr.assets.get('cash', 0))),
                    "frozen_cash": float(getattr(assets, 'frozen_cash', 0)),
                    "market_value": float(getattr(assets, 'market_value', 0)),
                    "total_asset": float(getattr(assets, 'total_asset', 0)),
                })
            else:
                self._log("[实盘] 资金查询返回 None，使用缓存值", "WARNING")
        except Exception as e:
            self._log(f"[实盘] 刷新资金失败，使用缓存值: {e}", "WARNING")

        try:
            # 刷新持仓
            positions = self.trader.query_stock_positions(self.account)
            if positions is not None:
                new_positions = {}
                for pos in positions:
                    code = getattr(pos, 'stock_code', '')
                    if not code:
                        continue
                    new_positions[code] = {
                        "account_type": xtconstant.SECURITY_ACCOUNT,
                        "account_id": self.config.account_id,
                        "stock_code": code,
                        "volume": int(getattr(pos, 'volume', 0)),
                        "can_use_volume": int(getattr(pos, 'can_use_volume', 0)),
                        "open_price": float(getattr(pos, 'open_price', 0)),
                        "market_value": float(getattr(pos, 'market_value', 0)),
                        "frozen_volume": int(getattr(pos, 'frozen_volume', 0)),
                        "on_road_volume": int(getattr(pos, 'on_road_volume', 0)),
                        "yesterday_volume": int(getattr(pos, 'yesterday_volume', 0)),
                        "avg_price": float(getattr(pos, 'avg_price', 0)),
                        "current_price": float(getattr(pos, 'current_price', 0)),
                    }
                self.trade_mgr.positions = new_positions
            else:
                self._log("[实盘] 持仓查询返回 None，使用缓存值", "WARNING")
        except Exception as e:
            self._log(f"[实盘] 刷新持仓失败，使用缓存值: {e}", "WARNING")

    # ------------------------------------------------------------------ #
    # 四、实盘成交/错误回调处理                                            #
    # ------------------------------------------------------------------ #

    def _on_live_trade(self, trade):
        """成交回报处理：更新委托状态和持仓/资金。"""
        try:
            order_id = getattr(trade, 'order_id', None)
            stock_code = getattr(trade, 'stock_code', '')
            traded_volume = int(getattr(trade, 'traded_volume', 0))
            traded_price = float(getattr(trade, 'traded_price', 0))
            order_type = getattr(trade, 'order_type', None)

            self._log(
                f"[实盘] 成交回报: {stock_code} | 方向={'买入' if order_type == xtconstant.STOCK_BUY else '卖出'} | "
                f"成交量={traded_volume} | 成交价={traded_price:.2f}",
                "INFO"
            )

            # 更新委托状态
            if order_id and order_id in self.trade_mgr.orders:
                order = self.trade_mgr.orders[order_id]
                order['traded_volume'] = order.get('traded_volume', 0) + traded_volume
                if order['traded_volume'] >= order.get('order_volume', traded_volume):
                    order['order_status'] = xtconstant.ORDER_SUCCEEDED
                else:
                    order['order_status'] = 'partial'

            # 成交后刷新真实账户状态（异步回调后立即同步）
            self._refresh_live_account()

        except Exception as e:
            self._log(f"[实盘] 处理成交回报异常: {e}", "ERROR")

    def _on_live_order_error(self, order_error):
        """委托错误回报处理：记录日志，标记委托为 failed。"""
        try:
            stock_code = getattr(order_error, 'stock_code', '')
            error_id = getattr(order_error, 'error_id', -1)
            error_msg = getattr(order_error, 'error_msg', '')
            order_remark = getattr(order_error, 'order_remark', '')

            self._log(
                f"[实盘] 委托错误: {stock_code} | error_id={error_id} | {error_msg} | 备注={order_remark}",
                "ERROR"
            )

            # 在 orders 中查找并标记为 failed（通过 order_remark 匹配）
            for oid, order in self.trade_mgr.orders.items():
                if order.get('stock_code') == stock_code and order.get('order_status') == 'pending':
                    order['order_status'] = 'failed'
                    order['error_msg'] = error_msg
                    break

        except Exception as e:
            self._log(f"[实盘] 处理委托错误回报异常: {e}", "ERROR")

    # ------------------------------------------------------------------ #
    # 五、辅助方法                                                         #
    # ------------------------------------------------------------------ #

    def _extract_bar_date(self, data: Dict) -> Optional[str]:
        """从行情推送数据中提取 bar 日期（'YYYY-MM-DD' 格式）。

        xtdata.subscribe_quote 回调的 data 结构为 {stock_code: DataFrame}，
        DataFrame 的索引或 'time' 列为时间戳。
        """
        try:
            for code, df in data.items():
                if not hasattr(df, 'index') or len(df) == 0:
                    continue
                # 取最后一行的时间
                last_idx = df.index[-1]
                ts = float(last_idx)
                if ts > 1e10:
                    ts = ts / 1000
                dt = datetime.datetime.fromtimestamp(ts)
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
        return None

    def _build_live_context(self, data: Dict) -> Dict:
        """构建与回测相同结构的 context 字典。"""
        now = datetime.datetime.now()
        time_info = {
            "timestamp": int(now.timestamp()),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        }

        context = {
            "__current_time__": time_info,
            "__account__": self.trade_mgr.assets,
            "__positions__": self.trade_mgr.positions,
            "__stock_list__": self.get_stock_list(),
            "__framework__": self,
        }

        # 将行情数据合并进 context
        if data:
            context.update(data)

        return context
