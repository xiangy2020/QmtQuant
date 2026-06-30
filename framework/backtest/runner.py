# coding: utf-8
"""
framework/backtest/runner.py
回测主流程 —— _run_backtest。
由 BacktestMixin 通过 mixin.py 引入，不可单独实例化。
"""
import os
import sys
import json
import logging
import time
import traceback
import datetime
import shutil
import hashlib
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from env import xtdata


def _get_custom_time_trigger_class():
    """延迟导入 CustomTimeTrigger，避免循环导入"""
    from framework.triggers import CustomTimeTrigger  # noqa: PLC0415
    return CustomTimeTrigger


def _safe_to_csv(self, df: pd.DataFrame, target_path: str, desc: str):
    """处理共享冲突时的容错写入"""
    for attempt in range(1, 4):
        try:
            df.to_csv(target_path, index=False, encoding='utf-8-sig')
            return
        except PermissionError:
            wait_time = 0.2 * attempt
            self.callbacks.on_log(
                f"{desc}保存失败（文件被占用），{wait_time:.1f}s后重试({attempt}/3)",
                "WARNING"
            )
            time.sleep(wait_time)
        except Exception as e:
            self._log(f"{desc}保存失败: {e}", "ERROR")
            raise


def _run_backtest(self):
    """回测模式"""
    try:
        # 检查数据周期和触发周期的一致性
        self._check_period_consistency()
        
        # 初始化回测记录字典
        self.backtest_records = {
            'trades': [],  # 交易记录
            'daily_stats': [],  # 每日统计数据
            'benchmark_data': [],  # 基准指数数据
            'start_time': self.config.backtest_start,
            'end_time': self.config.backtest_end,
            'init_capital': self.config.config_dict["backtest"]["init_capital"]
        }
        
        # 缓存日志开关状态，避免在回测循环中重复检查
        self._cache_should_log()

        self.callbacks.on_log("开始回测...", "INFO")

        # 基准标的代码（用于时间轴构建 + benchmark.csv 保存）
        benchmark_code = self.config.benchmark

        # 获取策略文件名（不含路径和扩展名）
        strategy_file = self.config.config_dict.get("strategy_file", "")
        strategy_name = os.path.splitext(os.path.basename(strategy_file))[0] if strategy_file else "unknown"
        
        self._log(f"策略文件路径: {strategy_file}", "INFO")
        self._log(f"解析的策略名称: {strategy_name}", "INFO")

        # 生成回测时间戳
        backtest_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 生成回测目录名（使用策略名称、回测时间范围和时间戳）
        # 为了避免调试器和中文路径的问题，直接使用ASCII安全的名称
        try:
            # 直接使用ASCII安全的策略名
            import hashlib
            strategy_hash = hashlib.md5(strategy_name.encode('utf-8')).hexdigest()[:8]
            backtest_dir_name = f"strategy_{strategy_hash}_{self.config.backtest_start}_{self.config.backtest_end}_{backtest_timestamp}"
            self._log(f"使用安全目录名: {backtest_dir_name} (原始策略名: {strategy_name})", "INFO")
        except Exception as e:
            self._log(f"生成目录名时出错: {str(e)}", "ERROR")
            # 使用默认名称
            backtest_dir_name = f"unknown_{self.config.backtest_start}_{self.config.backtest_end}_{backtest_timestamp}"
            self._log(f"使用默认目录名: {backtest_dir_name}", "INFO")

        # 确保backtest_results基础目录存在
        base_results_dir = "backtest_results"
        self._log(f"检查基础目录是否存在: {base_results_dir}", "INFO")
        try:
            if not os.path.exists(base_results_dir):
                os.makedirs(base_results_dir, exist_ok=True)
                self._log(f"创建基础回测目录: {base_results_dir}", "INFO")
            else:
                self._log(f"基础目录已存在: {base_results_dir}", "INFO")
        except Exception as e:
            self._log(f"检查/创建基础目录时出错: {str(e)}", "ERROR")
            raise
        
        # 构建回测结果目录路径
        backtest_dir = os.path.join(
            base_results_dir,
            backtest_dir_name
        )
        self._log(f"完整回测结果目录路径: {os.path.abspath(backtest_dir)}", "INFO")
        
        # 尝试规范化路径，处理可能的编码问题
        try:
            backtest_dir = os.path.normpath(backtest_dir)
            self._log(f"规范化后的路径: {backtest_dir}", "INFO")
        except Exception as e:
            self._log(f"路径规范化失败: {str(e)}", "ERROR")

        # 确保目录存在，增强错误处理
        try:
            # 强制使用绝对路径以增加稳健性
            if not os.path.isabs(backtest_dir):
                backtest_dir = os.path.abspath(backtest_dir)
                self._log(f"已将回测目录转换为绝对路径: {backtest_dir}", "INFO")

            self._log(f"准备检查目录是否存在: {backtest_dir}", "INFO")
            
            # 检测是否在调试模式下
            # 优先使用环境变量检测，这在编辑器调试模块中更可靠
            is_debugging = os.environ.get('QMTQUANT_DEBUG_MODE') == '1' or (hasattr(sys, 'gettrace') and sys.gettrace() is not None)
            
            if is_debugging:
                self._log(f"检测到调试模式，使用传统方法创建目录", "INFO")
                # 在调试模式下，直接尝试创建目录，不检查是否存在
                try:
                    # 使用exist_ok=True，如果目录已存在也不会报错
                    os.makedirs(backtest_dir, exist_ok=True)
                    self._log(f"已使用 os.makedirs 创建目录（或目录已存在）", "INFO")
                    time.sleep(0.2)
                except Exception as e:
                    self._log(f"创建目录时出错: {str(e)}", "ERROR")
                    # 尝试使用绝对路径
                    abs_backtest_dir = os.path.abspath(backtest_dir)
                    self._log(f"尝试使用绝对路径: {abs_backtest_dir}", "INFO")
                    os.makedirs(abs_backtest_dir, exist_ok=True)
                    backtest_dir = abs_backtest_dir
            else:
                # 非调试模式下可以使用pathlib
                from pathlib import Path
                backtest_path = Path(backtest_dir)
                self._log(f"使用 pathlib.Path 处理路径: {backtest_path}", "INFO")
                
                if not backtest_path.exists():
                    self._log(f"目录不存在，尝试创建: {backtest_path}", "INFO")
                    backtest_path.mkdir(parents=True, exist_ok=True)
                    self._log(f"已使用 Path.mkdir 创建目录", "INFO")
                    time.sleep(0.2)
                else:
                    self._log(f"目录已存在: {backtest_path}", "INFO")
                
                # 将路径转回字符串格式供后续使用
                backtest_dir = str(backtest_path)
            
            # 再次验证目录是否存在（调试模式下跳过）
            if not is_debugging:
                if not os.path.exists(backtest_dir):
                    self._log(f"目录创建后仍然不存在！", "ERROR")
                    raise FileNotFoundError(f"无法创建或访问回测结果目录: {backtest_dir}")
                self._log(f"回测结果目录确认存在: {backtest_dir}", "INFO")
            else:
                self._log(f"调试模式下跳过目录存在性验证", "INFO")
                self._log(f"假定回测结果目录已创建: {backtest_dir}", "INFO")
                
        except Exception as e:
            error_msg = f"创建回测结果目录时失败: {str(e)}"
            self._log(error_msg, "ERROR")
            raise Exception(error_msg)

        benchmark_file = os.path.join(backtest_dir, "benchmark.csv")

        if not os.path.exists(benchmark_file):
            self.callbacks.on_log(f"开始获取基准指数 {benchmark_code} 的每日数据", "INFO")
            
            try:
                benchmark_data = xtdata.get_market_data_ex(
                    field_list=['time', 'close'],
                    stock_list=[benchmark_code],
                    period='1d',
                    start_time=self.config.backtest_start,
                    end_time=self.config.backtest_end,
                )
                
                if not benchmark_data or benchmark_code not in benchmark_data:
                    self.callbacks.on_log(
                        f"基准指数 {benchmark_code} 本地无数据，请先通过数据管理功能补充该指数数据后再运行回测",
                        "WARNING"
                    )
                
                if benchmark_data and benchmark_code in benchmark_data:
                    df = benchmark_data[benchmark_code]
                    
                    self.callbacks.on_log(
                            f"基准数据形状: {df.shape}",
                            "INFO"
                        )
                    
                    # 确保有时间和收盘价列
                    if 'time' in df.columns and 'close' in df.columns:
                        # 转换时间戳为日期
                        try:
                            df['date'] = pd.to_datetime(df['time'], unit='ms')
                        except:
                            # 如果转换失败，尝试其他单位
                            try:
                                df['date'] = pd.to_datetime(df['time'], unit='s')
                            except:
                                try:
                                    df['date'] = pd.to_datetime(df['time'])
                                except Exception as e:
                                    self.callbacks.on_log(f"时间戳转换失败: {str(e)}", "ERROR")
                        
                        # 选择需要的列并保存
                        if 'date' in df.columns:
                            result_df = df[['date', 'close']].copy()
                            
                            if len(result_df) > 0:
                                # 确保保存目录存在
                                os.makedirs(os.path.dirname(benchmark_file), exist_ok=True)
                                result_df.to_csv(benchmark_file, index=False)
                                self.callbacks.on_log(
                                        f"基准指数数据已保存到 {benchmark_file}, 共 {len(result_df)} 条记录",
                                        "INFO"
                                    )
                                    
                                # 预先缓存所有基准指数数据，提高性能
                                for _, row in result_df.iterrows():
                                    date_str = row['date'].strftime('%Y%m%d')
                                    cache_key = f"benchmark_{date_str}_{benchmark_code}"
                                    self._cached_benchmark_close[cache_key] = row['close']
                                
                                self.callbacks.on_log(
                                        f"已预缓存 {len(self._cached_benchmark_close)} 条基准指数数据",
                                        "INFO"
                                    )
            except Exception:
                self.callbacks.on_log(
                    f"基准指数 {benchmark_code} 本地无数据，请先通过数据管理功能补充该指数数据后再运行回测",
                    "WARNING"
                )
        
        # ------------------------------------------------------------------ #
        # 构建时间轴：由基准标的驱动（CustomTimeTrigger 保留交易日历路径）    #
        # ------------------------------------------------------------------ #
        all_times = []

        CustomTimeTrigger = _get_custom_time_trigger_class()
        if isinstance(self.trigger, CustomTimeTrigger):
            # CustomTimeTrigger：使用交易日历 + 自定义时间点生成时间轴
            start_date = datetime.datetime.strptime(self.config.backtest_start, "%Y%m%d").date()
            end_date = datetime.datetime.strptime(self.config.backtest_end, "%Y%m%d").date()

            current_date = start_date
            trading_days = []
            while current_date <= end_date:
                date_str = current_date.strftime("%Y-%m-%d")
                if self.tools.is_trade_day(date_str):
                    trading_days.append(current_date)
                current_date += datetime.timedelta(days=1)

            self.callbacks.on_log(f"回测期间共有{len(trading_days)}个交易日", "INFO")

            for day in trading_days:
                for seconds in self.trigger.trigger_seconds:
                    h = seconds // 3600
                    m = (seconds % 3600) // 60
                    s = seconds % 60
                    dt = datetime.datetime.combine(day, datetime.time(h, m, s))
                    all_times.append(int(dt.timestamp()))

            self.callbacks.on_log(f"自定义时间触发模式：生成了{len(all_times)}个时间点", "INFO")
        else:
            # 其他触发器：仅拉取基准标的数据，用其 time 列构建时间轴
            data_period = self.trigger.get_data_period()
            self.callbacks.on_log(
                f"使用基准标的 {benchmark_code} 构建时间轴，数据周期: {data_period}", "INFO"
            )
            try:
                benchmark_timeline_data = xtdata.get_market_data_ex(
                    field_list=['time', 'close'],
                    stock_list=[benchmark_code],
                    period=data_period,
                    start_time=self.config.backtest_start,
                    end_time=self.config.backtest_end,
                )
            except Exception as e:
                self.callbacks.on_log(
                    f"拉取基准标的 {benchmark_code} 时间轴数据失败: {e}，"
                    f"请先通过数据管理功能补充该指数数据后再运行回测",
                    "ERROR"
                )
                return

            if not benchmark_timeline_data or benchmark_code not in benchmark_timeline_data:
                self.callbacks.on_log(
                    f"基准标的 {benchmark_code} 本地无数据，"
                    f"请先通过数据管理功能补充该指数数据后再运行回测",
                    "ERROR"
                )
                return

            bm_df = benchmark_timeline_data[benchmark_code]
            if len(bm_df) == 0:
                self.callbacks.on_log(
                    f"基准标的 {benchmark_code} 数据为空，无法构建时间轴",
                    "ERROR"
                )
                return

            # get_market_data_ex 返回的 DataFrame 中，time 是 index（毫秒时间戳），
            # 不是 columns 中的普通列。需从 index 提取时间戳。
            if 'time' in bm_df.columns:
                # 兼容极少数情况下 time 作为普通列存在
                raw_times = bm_df['time'].values
            else:
                # 标准情况：index 即为毫秒时间戳
                raw_times = bm_df.index.values

            # 统一转换为秒级整数时间戳（回测循环使用秒级）
            all_times = []
            for t in raw_times:
                try:
                    t_int = int(t)
                    if t_int > 1e10:  # 毫秒级 → 转为秒级
                        all_times.append(t_int // 1000)
                    else:
                        all_times.append(t_int)
                except Exception:
                    pass
            self.callbacks.on_log(
                f"基准标的时间轴构建完成，共 {len(all_times)} 个时间点", "INFO"
            )
        
        if len(all_times) == 0:
            self.callbacks.on_log("错误: 没有找到任何有效的时间点，无法进行回测", "ERROR")
            return
        
        self.callbacks.on_log(f"共找到{len(all_times)}个时间点", "INFO")
        self.callbacks.on_log(f"第一个时间点: {all_times[0]}", "INFO")
        self.callbacks.on_log(f"最后一个时间点: {all_times[-1]}", "INFO")
        
        # 保存所有时间点到实例变量，供record_results使用
        self.all_times = all_times
        
        total_times = len(all_times)
        processed_times = 0
        
        # 计算进度显示增量（至少为1，最多为总数/100向上取整）
        if total_times > 100:
            progress_increment = max(1, int(total_times / 100))
        else:
            # 如果时间点太少，则每处理一个点都显示一次进度
            progress_increment = 1
            
        # 显示开始进度
        self.callbacks.on_log("回测进度: 0.00%", "INFO")
        # 强制发送0%进度信号，确保进度条立即显示
        self.callbacks.on_progress(0)
        
        # 按时间顺序模拟
        current_date = None
        day_start_time = None
        day_data = {}
        
        # 获取盘前盘后回调设置
        pre_market_enabled = self.config.config_dict.get("market_callback", {}).get("pre_market_enabled", False)
        pre_market_time = self.config.config_dict.get("market_callback", {}).get("pre_market_time", "08:30:00")
        post_market_enabled = self.config.config_dict.get("market_callback", {}).get("post_market_enabled", False)
        post_market_time = self.config.config_dict.get("market_callback", {}).get("post_market_time", "15:30:00")
        
        if pre_market_enabled:
            self.callbacks.on_log(f"已启用盘前回调，将在每个交易日 {pre_market_time} 执行", "INFO")
            # 检查策略是否实现了盘前回调方法
            if not hasattr(self.strategy_module, 'on_pre_market'):
                self.callbacks.on_log("警告: 策略模块未实现 on_pre_market 方法，盘前回调将不会执行", "WARNING")
        if post_market_enabled:
            self.callbacks.on_log(f"已启用盘后回调，将在每个交易日 {post_market_time} 执行", "INFO")
            # 检查策略是否实现了盘后回调方法
            if not hasattr(self.strategy_module, 'on_post_market'):
                self.callbacks.on_log("警告: 策略模块未实现 on_post_market 方法，盘后回调将不会执行", "WARNING")
        
        # 获取唯一的交易日列表
        trading_days = set()
        for time_point in all_times:
            try:
                timestamp = int(time_point)
                # 判断时间戳精度（秒级或毫秒级）
                if timestamp > 1e10:  # 毫秒级时间戳
                    dt = datetime.datetime.fromtimestamp(timestamp / 1000)
                else:  # 秒级时间戳
                    dt = datetime.datetime.fromtimestamp(timestamp)
                trading_days.add(dt.strftime("%Y-%m-%d"))
            except:
                pass
        
        trading_days = sorted(list(trading_days))
        self.callbacks.on_log(f"回测期间共有 {len(trading_days)} 个交易日", "INFO")
        
        # 初始化时间统计变量
        time_stats = {
            "构造数据": 0,
            "构造时间信息": 0,
            "检查新日期": 0,
            "盘后回调": 0,
            "盘前回调": 0,
            "触发器检查": 0,
            "风控检查": 0,
            "策略处理": 0,
            "处理信号": 0,
            "交易指令": 0,
            "记录结果": 0,
            "总时间": 0
        }
        
        for current_time in all_times:
            loop_start_time = time.time()
            
            if not self.is_running:
                self.callbacks.on_log("回测被中止", "WARNING")
                break
                
            processed_times += 1
            # 根据计算的增量显示进度，但确保前几次都显示
            should_show_progress = False
            if processed_times <= 5:  # 前5次都显示
                should_show_progress = True
            elif processed_times % progress_increment == 0:  # 按增量显示
                should_show_progress = True
            elif processed_times == total_times:  # 最后一次也显示
                should_show_progress = True
            
            if should_show_progress:
                progress = (processed_times / total_times) * 100
                # 直接发送进度信号更新进度条（高效，不走日志系统）
                self.callbacks.on_progress(int(progress))
                # 只在需要输出日志时才记录进度文本
                if self._should_log():
                    self.callbacks.on_log(f"回测进度: {progress:.2f}%", "INFO")
            
            # 进一步优化的构造数据代码
            data_start_time = time.time()
            
            # 解析当前时间戳
            try:
                timestamp = int(current_time)
                if timestamp > 1e10:  # 毫秒级时间戳
                    dt = datetime.datetime.fromtimestamp(timestamp / 1000)
                else:  # 秒级时间戳
                    dt = datetime.datetime.fromtimestamp(timestamp)
                time_info = {
                    "timestamp": timestamp,
                    "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": dt.strftime("%Y-%m-%d"),
                    "time": dt.strftime("%H:%M:%S"),
                    "raw_time": current_time
                }
            except Exception:
                time_info = {
                    "timestamp": current_time,
                    "datetime": str(current_time),
                    "date": str(current_time),
                    "time": str(current_time),
                    "raw_time": current_time
                }

            # 通过 StockFilter 获取当前时间点关注的标的列表
            current_stock_list = self.stock_filter.get_stocks(current_time)

            # context 仅含元信息，不注入任何 bar 数据
            current_data = {"__current_time__": time_info}

            time_stats["构造数据"] += time.time() - data_start_time
            
            # time_info 已在数据构造段生成，直接复用
            time_info_start = time.time()
            time_stats["构造时间信息"] += time.time() - time_info_start

            # 注入账户、持仓、股票池元信息
            current_data["__account__"] = self.trade_mgr.assets
            current_data["__positions__"] = self.trade_mgr.positions
            current_data["__stock_list__"] = current_stock_list
            
            # 检查是否是新的一天
            new_day_start = time.time()
            if current_date != time_info["date"]:
                # 如果有前一天的数据，执行盘后回调
                post_market_start = time.time()
                if current_date is not None and post_market_enabled and hasattr(self.strategy_module, 'on_post_market'):
                    # 执行盘后回调
                    try:
                        self.callbacks.on_log(f"执行盘后回调 - 日期: {current_date}", "INFO")
                        
                        # 设置时间信息为盘后时间
                        post_time_info = time_info.copy()
                        post_time_info["time"] = post_market_time
                        post_time_info["datetime"] = f"{current_date} {post_market_time}"
                        
                        # 使用最后一个时间点的数据或创建一个完整的数据结构
                        post_data = day_data.copy() if day_data else {}
                        post_data["__current_time__"] = post_time_info
                        
                        # 添加账户和持仓信息到数据字典
                        post_data["__account__"] = self.trade_mgr.assets
                        post_data["__positions__"] = self.trade_mgr.positions
                        post_data["__stock_list__"] = current_stock_list
                        
                        # 添加框架实例到数据字典
                        post_data["__framework__"] = self
                        
                        # 执行盘后回调
                        post_signals = self.strategy_module.on_post_market(post_data)
                        
                        # 处理盘后回调产生的信号
                        if post_signals:
                            for signal in post_signals:
                                if 'price' in signal:
                                    signal['price'] = round(float(signal['price']), self.price_decimals)
                                signal['timestamp'] = time_info["timestamp"]
                            
                            # 发送交易指令
                            self.trade_mgr.process_signals(post_signals)
                    except Exception as e:
                        self.callbacks.on_log(f"执行盘后回调时出错: {str(e)}", "ERROR")
                time_stats["盘后回调"] += time.time() - post_market_start

                # 更新当前日期
                current_date = time_info["date"]
                day_start_time = time_info["timestamp"]
                day_data = current_data

                # T+1模式下，新交易日将 can_use_volume 更新为 volume
                if not self.trade_mgr.t0_mode:
                    for code, pos in self.trade_mgr.positions.items():
                        if pos.get("volume", 0) > 0:
                            pos["can_use_volume"] = pos["volume"]

                # 检查是否需要执行盘前回调
                pre_market_start = time.time()
                if pre_market_enabled and hasattr(self.strategy_module, 'on_pre_market'):
                    # 执行盘前回调
                    try:
                        self.callbacks.on_log(f"执行盘前回调 - 日期: {current_date}", "INFO")
                        
                        # 设置时间信息为盘前时间
                        pre_time_info = time_info.copy()
                        pre_time_info["time"] = pre_market_time
                        pre_time_info["datetime"] = f"{current_date} {pre_market_time}"
                        
                        # 使用当前时间点的数据或创建一个完整的数据结构
                        pre_data = current_data.copy()
                        pre_data["__current_time__"] = pre_time_info
                        
                        # 确保包含账户和持仓信息
                        pre_data["__account__"] = self.trade_mgr.assets
                        pre_data["__positions__"] = self.trade_mgr.positions
                        pre_data["__stock_list__"] = current_stock_list
                        
                        # 添加框架实例到数据字典
                        pre_data["__framework__"] = self
                        
                        # 执行盘前回调
                        pre_signals = self.strategy_module.on_pre_market(pre_data)
                        
                        # 处理盘前回调产生的信号
                        if pre_signals:
                            for signal in pre_signals:
                                if 'price' in signal:
                                    signal['price'] = round(float(signal['price']), self.price_decimals)
                                signal['timestamp'] = time_info["timestamp"]
                            
                            # 发送交易指令
                            self.trade_mgr.process_signals(pre_signals)
                    except Exception as e:
                        self.callbacks.on_log(f"执行盘前回调时出错: {str(e)}", "ERROR")
                time_stats["盘前回调"] += time.time() - pre_market_start
            else:
                # 更新当天的数据
                day_data = current_data
            time_stats["检查新日期"] += time.time() - new_day_start
            
            # 使用触发器判断是否应该触发策略
            trigger_start = time.time()
            if not self.trigger.should_trigger(current_time, current_data):
                time_stats["触发器检查"] += time.time() - trigger_start
                continue
            time_stats["触发器检查"] += time.time() - trigger_start
            
            # 风控检查
            risk_start = time.time()
            if not self.risk_mgr.check_risk(current_data):
                time_stats["风控检查"] += time.time() - risk_start
                continue
            time_stats["风控检查"] += time.time() - risk_start
            
            # 检查是否是交易日
            current_date_str = current_data.get("__current_time__", {}).get("date", "")
            if current_date_str and not self.tools.is_trade_day(current_date_str):
                # 如果不是交易日，跳过策略调用
                continue
            
            # 添加框架实例到数据字典
            current_data["__framework__"] = self
            
            # 调用策略处理
            strategy_start = time.time()
            try:
                signals = self.strategy_module.on_bar(current_data)
            except (ValueError, IndexError):
                # 数据量不足（如均线计算需要的历史数据不够），跳过该时间点
                time_stats["策略处理"] += time.time() - strategy_start
                continue
            time_stats["策略处理"] += time.time() - strategy_start
            
            # 处理信号中的价格精度
            signal_process_start = time.time()
            if signals:
                for signal in signals:
                    if 'price' in signal:
                        # 使用动态精度
                        signal['price'] = round(float(signal['price']), self.price_decimals)
                    # 添加当前回测时间戳
                    signal['timestamp'] = current_time
            time_stats["处理信号"] += time.time() - signal_process_start
            
            # 发送交易指令
            trade_start = time.time()
            if signals:
                self.trade_mgr.process_signals(signals)
            time_stats["交易指令"] += time.time() - trade_start
            
            # 记录结果
            record_start = time.time()
            self.record_results(current_time, current_data, signals)
            time_stats["记录结果"] += time.time() - record_start
            
            # 累计总时间
            time_stats["总时间"] += time.time() - loop_start_time
        
        # 输出时间统计信息
        total_time = time_stats["总时间"]
        if total_time > 0:
            self.callbacks.on_log("回测各部分执行时间统计:", "INFO")
            for key, value in time_stats.items():
                if key != "总时间":
                    percentage = (value / total_time) * 100
                    self.callbacks.on_log(f"{key}: {value:.4f}秒 ({percentage:.2f}%)", "INFO")
            self.callbacks.on_log(f"总执行时间: {total_time:.4f}秒", "INFO")
        
        # 处理最后一天的盘后回调
        if current_date is not None and post_market_enabled and hasattr(self.strategy_module, 'on_post_market'):
            try:
                self.callbacks.on_log(f"执行最后一天的盘后回调 - 日期: {current_date}", "INFO")
                
                # 设置时间信息为盘后时间
                time_info = (day_data.get("__current_time__", {}) if day_data else {}).copy()
                if not time_info:
                    # 如果没有时间信息，创建一个默认的
                    time_info = {
                        "timestamp": int(time.time()),
                        "date": current_date,
                        "time": post_market_time,
                        "datetime": f"{current_date} {post_market_time}"
                    }
                else:
                    time_info["time"] = post_market_time
                    time_info["datetime"] = f"{current_date} {post_market_time}"
                
                # 使用最后一个时间点的数据或创建一个完整的数据结构
                post_data = day_data.copy() if day_data else {}
                post_data["__current_time__"] = time_info
                
                # 添加账户和持仓信息到数据字典
                post_data["__account__"] = self.trade_mgr.assets
                post_data["__positions__"] = self.trade_mgr.positions
                post_data["__stock_list__"] = self.stock_filter.get_stocks(int(time.time()))
                
                # 添加框架实例到数据字典
                post_data["__framework__"] = self
                
                # 执行盘后回调
                post_signals = self.strategy_module.on_post_market(post_data)
                
                # 处理盘后回调产生的信号
                if post_signals:
                    for signal in post_signals:
                        if 'price' in signal:
                            signal['price'] = round(float(signal['price']), self.price_decimals)
                        signal['timestamp'] = time_info["timestamp"]
                    
                    # 发送交易指令
                    self.trade_mgr.process_signals(post_signals)
            except Exception as e:
                self.callbacks.on_log(f"执行最后一天的盘后回调时出错: {str(e)}", "ERROR")
            
        # 回测完成后通知调用方
        self.is_running = False
        self.callbacks.on_finished()
        self.callbacks.on_log("回测进度: 100.00%", "INFO")
        self.callbacks.on_log("回测完成", "INFO")
            
        # 在回测完成后保存回测记录
        self._save_backtest_results(backtest_dir_name)

    except Exception as e:
        error_msg = "回测运行异常: " + str(e)
        logging.error(error_msg, exc_info=True)
        # 调用错误回调函数
        self.callbacks.on_log(error_msg, "ERROR")
        import traceback
        self.callbacks.on_log(f"错误详情:\n{traceback.format_exc()}", "ERROR")
        raise  # 重新抛出异常

