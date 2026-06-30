# coding: utf-8
"""
framework/backtest/recorder.py
回测交易记录与每日统计 —— record_results、_record_daily_stats。
由 BacktestMixin 通过 mixin.py 引入，不可单独实例化。
"""
import logging
import datetime
import time

import numpy as np
import pandas as pd
from types import SimpleNamespace

from env import xtdata


def record_results(self, timestamp, data, signals):
    """记录回测结果
    
    Args:
        timestamp: 当前时间戳
        data: 当前市场数据
        signals: 交易信号列表
    """
    try:
        # 获取当前时间信息
        current_time_info = data.get("__current_time__", {})
        current_ts = current_time_info.get("timestamp", timestamp)
        current_datetime = current_time_info.get("datetime", "")
        current_date = current_time_info.get("date", "")
        current_time = current_time_info.get("time", "")
        
        # 检查是否是交易日
        is_trading_day = self.tools.is_trade_day(current_date)
        if not is_trading_day:
            # 如果不是交易日，则跳过策略调用
            if self._should_log():
                self.callbacks.on_log(f"日期 {current_date} 不是交易日，跳过策略执行", "INFO")
            return
        
        # 记录交易信号
        if signals:
            for signal in signals:
                if 'action' not in signal or 'code' not in signal:
                    continue
                    
                # 记录时间戳
                timestamp_ms = signal.get('timestamp', current_ts)
                # 如果时间戳是秒级，转换为毫秒级
                if timestamp_ms < 1e10:
                    timestamp_ms *= 1000
        
        # 1. 时间戳处理优化 - 使用缓存和类型检查优化
        if isinstance(timestamp, str):
            if hasattr(self, '_cached_timestamp') and self._cached_timestamp.get('str') == timestamp:
                current_time = self._cached_timestamp.get('datetime')
                current_date = self._cached_timestamp.get('date')
                current_ts_seconds = self._cached_timestamp.get('ts_seconds')
            else:
                current_time = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                current_date = current_time.date()
                current_ts_seconds = current_time.timestamp()
                self._cached_timestamp = {
                    'str': timestamp,
                    'datetime': current_time,
                    'date': current_date,
                    'ts_seconds': current_ts_seconds
                }
        else:
            # 数字时间戳处理
            ts_float = float(timestamp)
            # 统一转换为秒级时间戳
            ts_seconds = ts_float / 1000 if ts_float > 1e10 else ts_float
            
            # 使用缓存检查是否与上次时间戳相近（避免重复转换相近时间戳）
            if hasattr(self, '_cached_timestamp') and abs(self._cached_timestamp.get('ts_seconds', 0) - ts_seconds) < 0.1:
                current_time = self._cached_timestamp.get('datetime')
                current_date = self._cached_timestamp.get('date')
                current_ts_seconds = self._cached_timestamp.get('ts_seconds')
            else:
                current_time = datetime.datetime.fromtimestamp(ts_seconds)
                current_date = current_time.date()
                current_ts_seconds = ts_seconds
                self._cached_timestamp = {
                    'ts_seconds': ts_seconds,
                    'datetime': current_time,
                    'date': current_date
                }
        
        # 2. 交易日检查优化 - 使用缓存避免重复查询
        cache_key = f"trade_day_{current_date}"
        if hasattr(self, '_cached_trade_days') and cache_key in self._cached_trade_days:
            is_trading_day = self._cached_trade_days[cache_key]
        else:
            if not hasattr(self, '_cached_trade_days'):
                self._cached_trade_days = {}
                
            try:
                # 使用QuTools的is_trade_day方法进行统一的交易日判断
                date_str = current_date.strftime("%Y-%m-%d")
                is_trading_day = self.tools.is_trade_day(date_str)
                # 缓存结果
                self._cached_trade_days[cache_key] = is_trading_day
            except Exception as e:
                logging.warning(f"检查交易日失败: {str(e)}")
                is_trading_day = True  # 出错默认为交易日
                
        # 3. 持仓更新优化 - 预先获取并缓存持仓列表
        positions = self.trade_mgr.positions
        position_codes = list(positions.keys())
        
        # 4. 非交易日处理优化
        if not is_trading_day:
            # 非交易日情况下，不更新持仓市值
            # 只记录每日统计数据，使用前一个交易日的市值数据
            total_market_value = 0.0
            for code, position in positions.items():
                # 使用已记录的市值，不从当天数据获取
                if 'market_value' in position and position['market_value'] > 0:
                    total_market_value += position['market_value']
        else:
            # 5. 交易日市值计算优化
            # context 中不再有 bar 数据，使用持仓中已记录的 current_price
            # （current_price 由 _record_daily_stats 通过独立日线拉取更新）
            total_market_value = 0.0
            for code in position_codes:
                position = positions[code]
                # 优先使用 data 中缓存的 bar（由 get_price 按需拉取后写入）
                if code in data and isinstance(data[code], pd.Series) and not data[code].empty:
                    bar = data[code]
                    try:
                        current_price = float(bar.get('close', bar.get('lastPrice', 0)) or 0)
                    except (TypeError, ValueError):
                        current_price = 0.0
                    if current_price <= 0:
                        current_price = position.get('current_price', position.get('avg_price', 0))
                else:
                    # 使用持仓中已有的价格（由上一个交易日 _record_daily_stats 更新）
                    current_price = position.get('current_price', position.get('avg_price', 0))

                volume = position['volume']
                avg_price = position['avg_price']

                market_value = current_price * volume
                position['market_value'] = market_value
                if current_price > 0:
                    position['current_price'] = current_price
                position['profit'] = (current_price - avg_price) * volume
                position['profit_ratio'] = (current_price - avg_price) / avg_price if avg_price != 0 else 0

                total_market_value += market_value
        
        # 6. 资产更新优化
        assets = self.trade_mgr.assets
        old_total_asset = assets.get('total_asset', 0)
        old_market_value = assets.get('market_value', 0)
        
        # 非交易日且没有交易信号时，市值保持不变
        if not is_trading_day and not signals and old_market_value > 0:
            total_market_value = old_market_value
        
        # 更新资产信息
        assets['market_value'] = total_market_value
        assets['total_asset'] = assets['cash'] + total_market_value
        
        # 只在资产变化显著时触发回调，减少不必要的回调
        # 回测模式下无实盘交易回调，跳过
        
        # 7. 交易信号处理优化
        if signals:
            trade_mgr = self.trade_mgr
            # 提前获取资产数据
            total_asset = assets['total_asset']
            cash = assets['cash']
            market_value = assets['market_value']
            
            # 使用列表推导式批量处理信号
            self.backtest_records['trades'].extend([
                {
                    'datetime': current_time,
                    'code': signal['code'],
                    'action': signal['action'],
                    'price': signal.get('actual_price', signal['price']),
                    'volume': signal['volume'],
                    'amount': signal.get('actual_price', signal['price']) * signal['volume'],
                    'commission': (
                        signal.get('trade_cost', 0) * (trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume']) /
                        (trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action']) +
                        trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_flow_fee()))
                        if 'trade_cost' in signal else
                        trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume'])
                    ),
                    'stamp_tax': (
                        signal.get('trade_cost', 0) * (trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action']) /
                        (trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action']) +
                        trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_flow_fee()))
                        if 'trade_cost' in signal and signal['action'] == 'sell' else
                        trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action'])
                    ),
                    'transfer_fee': (
                        signal.get('trade_cost', 0) * (trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume']) /
                        (trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action']) +
                        trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_flow_fee()))
                        if 'trade_cost' in signal and signal['code'].startswith("sh.") else
                        trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume'])
                    ),
                    'flow_fee': (
                        signal.get('trade_cost', 0) * (trade_mgr.calculate_flow_fee() /
                        (trade_mgr.calculate_commission(signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_stamp_tax(signal.get('actual_price', signal['price']), signal['volume'], signal['action']) +
                        trade_mgr.calculate_transfer_fee(signal['code'], signal.get('actual_price', signal['price']), signal['volume']) +
                        trade_mgr.calculate_flow_fee()))
                        if 'trade_cost' in signal else
                        trade_mgr.calculate_flow_fee()
                    ),
                    'total_asset': total_asset,
                    'cash': cash,
                    'market_value': market_value
                }
                for signal in signals
            ])
        
        # 8. 最后时间点判断优化
        is_last_time_point = False
        
        if type(self.trigger).__name__ == 'CustomTimeTrigger':
            # 对于自定义时间触发，使用缓存优化
            trigger_seconds = self.trigger.trigger_seconds
            if trigger_seconds:
                # 缓存当天的触发时间点
                cache_key = f"time_points_{current_date}"
                if not hasattr(self, '_cached_time_points') or cache_key not in self._cached_time_points:
                    if not hasattr(self, '_cached_time_points'):
                        self._cached_time_points = {}
                        
                    # 获取当天所有触发时间点并缓存
                    max_trigger_second = max(trigger_seconds)
                    
                    # 使用列表推导式优化循环
                    today_times = [
                        int(datetime.datetime.combine(current_date, datetime.time(
                            seconds // 3600,
                            (seconds % 3600) // 60,
                            seconds % 60
                        )).timestamp())
                        for seconds in trigger_seconds
                    ]
                    
                    # 缓存计算结果
                    self._cached_time_points[cache_key] = {
                        'times': sorted(today_times),
                        'max_second': max_trigger_second
                    }
                
                # 使用缓存数据
                max_trigger_second = self._cached_time_points[cache_key]['max_second']
                
                # 计算当前时间点的秒数(使用已有变量避免重复计算)
                current_ts_dt = current_time
                current_seconds = current_ts_dt.hour * 3600 + current_ts_dt.minute * 60 + current_ts_dt.second
                
                # 检查是否是当天最后一个触发点
                is_last_time_point = abs(current_seconds - max_trigger_second) < 0.1
        else:
            # 非自定义时间触发，使用all_times缓存优化
            cache_key = f"daily_times_{current_date}"
            if not hasattr(self, '_cached_daily_times') or cache_key not in self._cached_daily_times:
                if not hasattr(self, '_cached_daily_times'):
                    self._cached_daily_times = {}
                    
                # 获取当天的时间点，使用生成器表达式优化
                today_times = []
                
                # 使用列表推导式和异常处理优化
                try:
                    today_times = [
                        t for t in self.all_times
                        if datetime.datetime.fromtimestamp(
                            float(t) / 1000 if float(t) > 1e10 else float(t)
                        ).date() == current_date
                    ]
                except Exception:
                    # 出错时使用传统循环方式作为备选
                    for t in self.all_times:
                        try:
                            t_float = float(t)
                            t_seconds = t_float / 1000 if t_float > 1e10 else t_float
                            t_time = datetime.datetime.fromtimestamp(t_seconds)
                            
                            if t_time.date() == current_date:
                                today_times.append(t)
                        except Exception:
                            continue
                
                # 缓存结果
                self._cached_daily_times[cache_key] = sorted(today_times)
            
            # 使用缓存的时间点
            today_times = self._cached_daily_times[cache_key]
            
            # 检查是否是最后时间点
            if today_times:
                # 直接使用数值比较，避免创建新的datetime对象
                last_time = float(today_times[-1])
                last_time_seconds = last_time / 1000 if last_time > 1e10 else last_time
                is_last_time_point = abs(last_time_seconds - current_ts_seconds) < 0.1
        
        # 9. 每日统计记录优化 - 只在最后时间点记录
        if is_last_time_point and is_trading_day:
            self._record_daily_stats(current_date, current_time, data)
        
    except Exception as e:
        self.callbacks.on_log(f"记录回测结果时出错: {str(e)}", "ERROR")
        logging.error(f"记录回测结果时出错: {str(e)}", exc_info=True)


def _record_daily_stats(self, current_date, current_time, data):
    """记录每日统计数据（从record_results中分离出来的功能）
    
    Args:
        current_date: 当前日期
        current_time: 当前时间对象
        data: 市场数据
    """
    # 获取必要的资产数据
    assets = self.trade_mgr.assets
    cash = assets['cash']
    
    # 确保日期是字符串格式
    date_str = current_date
    if not isinstance(current_date, str):
        try:
            date_str = current_date.strftime("%Y-%m-%d") if hasattr(current_date, 'strftime') else str(current_date)
        except:
            date_str = str(current_date)
    
    # 重新计算一天结束时的市值
    positions = self.trade_mgr.positions
    position_codes = list(positions.keys())
    day_end_market_value = 0.0
    
    # 转换日期为YYYYMMDD格式，用于获取日线数据
    yyyymmdd_date = date_str.replace('-', '') if '-' in date_str else date_str
    
    # 批量获取收盘价
    daily_prices = {}
    if position_codes:
        # 检查缓存中是否已有当日数据
        cache_date_key = f"daily_prices_{yyyymmdd_date}"
        if cache_date_key in self.daily_price_cache:
            # 直接使用缓存中的数据
            daily_prices = self.daily_price_cache[cache_date_key]
            self.callbacks.on_log(f"使用缓存的日线数据，日期: {yyyymmdd_date}", "INFO")
        else:
            try:
                # 一次性获取所有持仓股票的日线数据
                daily_data = xtdata.get_market_data(
                    field_list=['close'],
                    stock_list=position_codes,
                    period='1d',
                    start_time=yyyymmdd_date,
                    end_time=yyyymmdd_date,
                    # 与回测数据保持一致的复权方式，避免"下单用复权价、估值用未复权价"的不一致
                    dividend_type=self.config.config_dict["data"].get("dividend_type", "none")
                )
                
                # 优化数据提取逻辑
                if daily_data is not None and isinstance(daily_data, dict) and 'close' in daily_data:
                    close_data = daily_data['close']
                    # 检查close_data的类型
                    if isinstance(close_data, pd.DataFrame):
                        # 使用向量化操作处理DataFrame
                        if any(code in close_data.index for code in position_codes):
                            latest_date = close_data.columns[-1]
                            # 使用向量化操作获取所有股票的价格
                            valid_codes = [code for code in position_codes if code in close_data.index]
                            daily_prices.update({
                                code: close_data.loc[code, latest_date]
                                for code in valid_codes
                                if close_data.loc[code, latest_date] is not None and close_data.loc[code, latest_date] > 0
                            })
                
                # 缓存获取的数据，避免同一天重复请求
                self.daily_price_cache[cache_date_key] = daily_prices
            except Exception as e:
                logging.error(f"获取日线数据失败: {e}")
    
    # 批量计算持仓市值
    for code in position_codes:
        # 优先使用日线收盘价
        if code in daily_prices and daily_prices[code] > 0:
            current_price = daily_prices[code]
        # 备选方案：使用 data 中缓存的 bar（由 get_price 按需拉取后写入）
        elif code in data and isinstance(data[code], pd.Series) and not data[code].empty:
            bar = data[code]
            try:
                current_price = float(bar.get('close', bar.get('lastPrice', 0)) or 0)
            except (TypeError, ValueError):
                current_price = 0.0
            if current_price <= 0:
                current_price = positions[code].get('current_price', positions[code].get('avg_price', 0))
        # 备选方案：使用持仓记录的价格
        elif 'current_price' in positions[code] and positions[code]['current_price'] > 0:
            current_price = positions[code]['current_price']
        # 最后备选：使用持仓均价
        else:
            current_price = positions[code]['avg_price']
        
        # 计算市值
        volume = positions[code]['volume']
        market_value = current_price * volume
        day_end_market_value += market_value
        
        # 更新持仓信息
        positions[code]['current_price'] = current_price
        positions[code]['market_value'] = market_value
        
        # 计算盈亏
        avg_price = positions[code]['avg_price']
        positions[code]['profit'] = (current_price - avg_price) * volume
        positions[code]['profit_ratio'] = (current_price - avg_price) / avg_price if avg_price > 0 else 0
    
    # 计算总资产
    total_asset = cash + day_end_market_value
    
    # 获取基准指数收盘价 - 使用缓存优化
    benchmark_code = self.config.config_dict["backtest"]["benchmark"]
    benchmark_close = None
    
    # 使用缓存避免重复获取基准数据
    cache_key = f"benchmark_{yyyymmdd_date}_{benchmark_code}"
    if cache_key in self._cached_benchmark_close:
        benchmark_close = self._cached_benchmark_close[cache_key]
    else:
        # 尝试从 data 中缓存的 bar 获取（由 get_price 按需拉取后写入）
        try:
            if benchmark_code in data and isinstance(data[benchmark_code], pd.Series) and not data[benchmark_code].empty:
                bar = data[benchmark_code]
                try:
                    v = float(bar.get('close', bar.get('lastPrice', 0)) or 0)
                    if v > 0:
                        benchmark_close = v
                        self._cached_benchmark_close[cache_key] = benchmark_close
                except (TypeError, ValueError):
                    pass
        except Exception as e:
            logging.debug(f"从 data 获取基准指数数据失败: {e}")
    
    # 计算当日收益率
    daily_stats = self.backtest_records['daily_stats']
    if daily_stats:
        prev_asset = daily_stats[-1]['total_asset']
        daily_return = (total_asset - prev_asset) / prev_asset if prev_asset != 0 else 0
    else:
        init_capital = self.backtest_records['init_capital']
        daily_return = (total_asset - init_capital) / init_capital if init_capital != 0 else 0
    
    # 创建持仓快照
    positions_snapshot = {
        code: {
            'volume': pos['volume'],
            'price': pos['current_price'],
            'avg_price': pos['avg_price'],
            'market_value': pos['market_value'],
            'profit': pos['profit'],
            'profit_ratio': pos['profit_ratio']
        }
        for code, pos in self.trade_mgr.positions.items()
    }
    
    # 记录每日统计数据
    daily_stat = {
        'date': current_date,
        'total_asset': total_asset,
        'cash': cash,
        'market_value': day_end_market_value,
        'daily_return': daily_return,
        'benchmark_close': benchmark_close,
        'positions': positions_snapshot
    }
    self.backtest_records['daily_stats'].append(daily_stat)
    
    # 记录基准指数数据
    if benchmark_close is not None:
        self.backtest_records['benchmark_data'].append({
            'date': current_date,
            'close': benchmark_close
        })
    
    # 输出日志（性能优化：检查是否需要输出）
    if self._should_log():
        decimals = self.price_decimals
        self.callbacks.on_log(
            f"每日统计 - 日期: {daily_stat['date']} | "
            f"总资产: {total_asset:.{decimals}f} | "
            f"日收益率: {daily_return*100:.2f}% | "
            f"持仓市值: {day_end_market_value:.{decimals}f} | "
            f"可用资金: {cash:.{decimals}f}",
            "INFO"
        )
