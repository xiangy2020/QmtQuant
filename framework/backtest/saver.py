# coding: utf-8
"""
framework/backtest/saver.py
回测结果保存 —— _save_backtest_results。
由 BacktestMixin 通过 mixin.py 引入，不可单独实例化。
"""
import os
import logging
import datetime
import shutil

import pandas as pd

from env import xtdata
from framework.backtest.runner import _safe_to_csv


def _save_backtest_results(self, backtest_dir_name: str):
    """保存回测结果到磁盘（交易记录、每日统计、汇总指标、策略文件等）。

    Args:
        backtest_dir_name: 回测结果目录名（由 _run_backtest 生成）
    """
    try:
        # 获取策略文件名（不含路径和扩展名）
        strategy_file = self.config.config_dict.get("strategy_file", "")
        strategy_name = os.path.splitext(os.path.basename(strategy_file))[0] if strategy_file else "unknown"
        
        # 生成回测时间戳
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 创建当前回测的子目录（包含策略名）
        backtest_dir = os.path.join(
            "backtest_results",
            backtest_dir_name
        )

        # 创建新目录（由于包含时间戳，目录名唯一，无需删除）
        os.makedirs(backtest_dir, exist_ok=True)

        # 保存交易记录
        trades_df = pd.DataFrame(self.backtest_records['trades'])
        if len(trades_df) == 0:
            trades_df = pd.DataFrame(columns=[
                'datetime', 'code', 'action', 'price', 'volume', 'amount',
                'commission', 'stamp_tax', 'transfer_fee', 'flow_fee',
                'total_asset', 'cash', 'market_value'
            ])
            self.callbacks.on_log("回测期间没有产生交易记录", "WARNING")
        _safe_to_csv(self, trades_df, os.path.join(backtest_dir, "trades.csv"), "交易记录")

        # 保存每日统计数据
        daily_stats_df = pd.DataFrame(self.backtest_records['daily_stats'])
        if len(daily_stats_df) == 0:
            daily_stats_df = pd.DataFrame(columns=[
                'date', 'total_asset', 'cash', 'market_value', 
                'daily_return', 'benchmark_close', 'positions'
            ])
            self.callbacks.on_log("回测期间没有产生每日统计数据", "WARNING")
        _safe_to_csv(self, daily_stats_df, os.path.join(backtest_dir, "daily_stats.csv"), "每日统计数据")

        # 保存回测汇总指标
        try:
            if len(daily_stats_df) >= 1:
                init_capital = self.backtest_records['init_capital']
                final_capital = daily_stats_df['total_asset'].iloc[-1]
                trade_days = len(daily_stats_df)

                # 计算总收益率
                total_return = (final_capital - init_capital) / init_capital * 100 if init_capital > 0 else 0

                # 计算年化收益率: ((1+R)^(250/n)-1)*100%
                if trade_days > 0 and init_capital > 0:
                    total_return_decimal = (final_capital / init_capital) - 1
                    annual_return = (pow(1 + total_return_decimal, 250/trade_days) - 1) * 100
                else:
                    annual_return = 0

                # 计算最大回撤
                cummax = daily_stats_df['total_asset'].cummax()
                drawdown = (cummax - daily_stats_df['total_asset']) / cummax * 100
                max_drawdown = drawdown.max()

                # 构建基准 DataFrame（来自 backtest_records）
                benchmark_records = self.backtest_records.get('benchmark_data', [])
                benchmark_df_for_metrics = pd.DataFrame(benchmark_records) if benchmark_records else None

                # 读取无风险利率（由 run() 传入，默认 0.03）
                risk_free_rate = getattr(self, '_risk_free_rate', 0.03)

                # 计算全量评估指标
                extra_metrics = self._calc_summary_metrics(
                    daily_stats_df=daily_stats_df,
                    trades_df=trades_df,
                    benchmark_df=benchmark_df_for_metrics,
                    annual_return=annual_return,
                    risk_free_rate=risk_free_rate,
                )

                # 保存汇总指标（基础 + 全量评估指标）
                summary = {
                    'init_capital': init_capital,
                    'final_capital': final_capital,
                    'total_return': total_return,
                    'annual_return': annual_return,
                    'max_drawdown': max_drawdown,
                    'trade_days': trade_days,
                    **extra_metrics,
                }
                _safe_to_csv(self, pd.DataFrame([summary]), os.path.join(backtest_dir, "summary.csv"), "回测汇总")
        except Exception as e:
            logging.warning(f"保存回测汇总指标时出错: {str(e)}")

        # 保存基准指数数据
        benchmark_code = self.config.config_dict["backtest"]["benchmark"]
        try:
            benchmark_data = xtdata.get_market_data(
                field_list=['close'],
                stock_list=[benchmark_code],
                period='1d',
                start_time=self.config.backtest_start,
                end_time=self.config.backtest_end,
            )

            if not benchmark_data or 'close' not in benchmark_data or len(benchmark_data['close']) == 0:
                self.callbacks.on_log(
                    f"基准指数 {benchmark_code} 本地无数据，请先通过数据管理功能补充该指数数据后再运行回测",
                    "WARNING"
                )
            elif benchmark_data and 'close' in benchmark_data and len(benchmark_data['close']) > 0:
                # get_market_data 返回结构固定：日期作为 DataFrame 的列名（YYYYMMDD 整数）
                df_close = benchmark_data['close']
                date_cols = [col for col in df_close.columns if str(col).isdigit()]
                if date_cols:
                    dates = pd.to_datetime(date_cols, format='%Y%m%d')
                    closes = df_close.iloc[0][date_cols].values

                    df = pd.DataFrame({'date': dates, 'close': closes})
                    benchmark_file = os.path.join(backtest_dir, "benchmark.csv")
                    _safe_to_csv(self, df, benchmark_file, "基准数据")
                    self.callbacks.on_log(
                        f"基准指数数据已保存到 {benchmark_file}, 共 {len(df)} 条记录",
                        "INFO"
                    )
                else:
                    self.callbacks.on_log(f"基准指数 {benchmark_code} 收盘价数据为空", "WARNING")
            else:
                self.callbacks.on_log(f"基准指数 {benchmark_code} 数据获取失败", "WARNING")
        except Exception as e:
            self.callbacks.on_log(f"获取基准指数数据时出错: {str(e)}", "ERROR")
            logging.error(f"获取基准指数数据时出错: {str(e)}", exc_info=True)
        
        # 保存策略文件副本
        strategy_file_path = self.config.config_dict.get("strategy_file", "")
        if strategy_file_path and os.path.exists(strategy_file_path):
            try:
                # 保存.py文件
                strategy_filename = os.path.basename(strategy_file_path)
                strategy_backup_path = os.path.join(backtest_dir, strategy_filename)
                shutil.copy2(strategy_file_path, strategy_backup_path)
                
                # 查找并保存对应的.qmt文件
                qmt_file_path = os.path.splitext(strategy_file_path)[0] + ".qmt"
                if os.path.exists(qmt_file_path):
                    qmt_filename = os.path.basename(qmt_file_path)
                    qmt_backup_path = os.path.join(backtest_dir, qmt_filename)
                    shutil.copy2(qmt_file_path, qmt_backup_path)
                    self.callbacks.on_log(f"策略配置文件已保存: {qmt_filename}", "INFO")
                
                self.callbacks.on_log(f"策略文件已保存: {strategy_filename}", "INFO")
                    
            except Exception as e:
                self.callbacks.on_log(f"保存策略文件时出错: {str(e)}", "ERROR")
                logging.error(f"保存策略文件时出错: {str(e)}", exc_info=True)
        
        # 保存完整的配置文件副本
        try:
            config_file_path = getattr(self.config, 'config_path', None)
            if config_file_path and os.path.exists(config_file_path):
                config_filename = os.path.basename(config_file_path)
                config_backup_path = os.path.join(backtest_dir, f"full_{config_filename}")
                shutil.copy2(config_file_path, config_backup_path)
                self.callbacks.on_log(f"完整配置文件已保存: full_{config_filename}", "INFO")
        except Exception as e:
            self.callbacks.on_log(f"保存完整配置文件时出错: {str(e)}", "ERROR")
            logging.error(f"保存完整配置文件时出错: {str(e)}", exc_info=True)
        
        # 保存回测配置信息
        config_info = {
            'start_time': self.backtest_records['start_time'],
            'end_time': self.backtest_records['end_time'],
            'init_capital': self.backtest_records['init_capital'],
            'benchmark': self.config.config_dict["backtest"]["benchmark"],
            'strategy_file': self.config.config_dict.get("strategy_file", ""),
            'actual_start_time': datetime.datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "",
            'actual_end_time': datetime.datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%d %H:%M:%S") if self.end_time else "",
            'total_runtime_seconds': self.total_runtime,
            'total_runtime_formatted': self._format_runtime(self.total_runtime),
            # 保存股票池信息
            'stock_list': ','.join(self.get_stock_list()) if hasattr(self, 'get_stock_list') else '',
            'min_volume': self.config.config_dict["backtest"].get("min_volume", 100),
            'kline_period': self.config.config_dict["data"].get("kline_period", "1m"),
            'dividend_type': self.config.config_dict["data"].get("dividend_type", "front")
        }
        _safe_to_csv(self, pd.DataFrame([config_info]), os.path.join(backtest_dir, "config.csv"), "配置数据")
        
        self.callbacks.on_log(
            f"回测记录已保存到目录: {backtest_dir}",
            "INFO"
        )
        # 记录回测总耗时
        self.callbacks.on_log(
            f"回测总耗时: {self._format_runtime(self.total_runtime)}",
            "INFO"
        )
            # 通知外部显示回测结果
        if hasattr(self.callbacks, 'on_backtest_result'):
            self.callbacks.on_backtest_result(backtest_dir)
        
    except Exception as e:
        self.callbacks.on_log(f"保存回测记录时出错: {str(e)}", "ERROR")
        logging.error(f"保存回测记录时出错: {str(e)}", exc_info=True)
