# -*- coding: utf-8 -*-
"""
framework/lifecycle.py
生命周期控制 Mixin —— stop、check_connection、reconnect 等运行控制方法，
以及 on_stock_order、on_stock_trade、on_stock_position、on_stock_asset 等交易事件处理方法。
由 QuantFramework 通过多继承引入，不可单独实例化。
"""
import os
import time
import logging
import traceback
from datetime import datetime
from typing import Dict

class LifecycleMixin:
    """生命周期控制 Mixin"""

    def _run_simulate(self):
        """模拟模式"""
        # 模拟相关逻辑实现
        pass

    def stop(self):
        """停止框架"""
        self.is_running = False
        
        # 记录结束时间（如果还没有记录的话）
        if self.end_time is None:
            self.end_time = time.time()
            if self.start_time is not None:
                self.total_runtime = self.end_time - self.start_time
                
                end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log(f"策略手动停止时间: {end_datetime}", "INFO")
                self._log(f"策略总运行时长: {self._format_runtime(self.total_runtime)}", "INFO")
        
        if self.trader:
            self.trader.stop()
            
    def check_connection(self) -> bool:
        """检查连接状态"""
        # 实现连接检查逻辑
        pass
        
    def reconnect(self):
        """重新连接"""
        try:
            self.init_trader_and_account()
        except Exception as e:
            self._log(f"重连失败: {str(e)}", "ERROR")
            
    def log_error(self, msg: str):
        """错误日志"""
        self._log(msg, "ERROR")

    def _format_runtime(self, seconds):
        """格式化运行时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours}小时{minutes}分钟{seconds}秒"
    
    def on_stock_position(self, position):
        """持仓变动回调"""
        try:
            decimals = self.price_decimals
            position_msg = (
                f"持仓变动 - "
                f"股票代码: {position.stock_code} | "
                f"持仓数量: {position.volume} | "
                f"可用数量: {position.can_use_volume} | "
                f"持仓均价: {position.avg_price:.{decimals}f} | "
                f"市值: {position.market_value:.{decimals}f}"
            )
            self._log(position_msg, "TRADE")
        except Exception as e:
            self._log(f"处理持仓变动回调时出错: {str(e)}", "ERROR")
    
    def on_order_error(self, error):
        """委托错误回调"""
        try:
            error_msg = (
                f"委托错误 - "
                f"股票代码: {error.stock_code} | "
                f"错误代码: {error.error_id} | "
                f"错误信息: {error.error_msg} | "
                f"备注: {error.order_remark}"
            )
            self._log(error_msg, "ERROR")
        except Exception as e:
            self._log(f"处理委托错误回调时出错: {str(e)}", "ERROR")
    
    def on_stock_order(self, order):
        """委托回报回调"""
        try:
            order_msg = (
                f"委托回报 - "
                f"股票代码: {order.stock_code} | "
                f"委托编号: {getattr(order, 'order_id', 'N/A')} | "
                f"状态: {getattr(order, 'order_status', 'N/A')} | "
                f"委托价格: {getattr(order, 'price', 'N/A')} | "
                f"委托数量: {getattr(order, 'order_volume', 'N/A')}"
            )
            self._log(order_msg, "TRADE")
        except Exception as e:
            self._log(f"处理委托回报时出错: {str(e)}", "ERROR")
    
    def on_stock_trade(self, trade):
        """成交回报回调"""
        try:
            trade_msg = (
                f"成交回报 - "
                f"股票代码: {trade.stock_code} | "
                f"成交价格: {getattr(trade, 'traded_price', 'N/A')} | "
                f"成交数量: {getattr(trade, 'traded_volume', 'N/A')} | "
                f"成交金额: {getattr(trade, 'traded_amount', 'N/A')}"
            )
            self._log(trade_msg, "TRADE")
        except Exception as e:
            self._log(f"处理成交回报时出错: {str(e)}", "ERROR")
    
    def on_stock_asset(self, asset):
        """资产变动回调"""
        try:
            asset_msg = (
                f"资产变动 - "
                f"总资产: {getattr(asset, 'total_asset', 'N/A')} | "
                f"现金: {getattr(asset, 'cash', 'N/A')} | "
                f"市值: {getattr(asset, 'market_value', 'N/A')}"
            )
            self._log(asset_msg, "INFO")
        except Exception as e:
            self._log(f"处理资产变动时出错: {str(e)}", "ERROR")
