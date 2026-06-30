# -*- coding: utf-8 -*-
"""
framework/triggers.py
触发器体系 —— TriggerBase、TickTrigger、KLineTrigger、CustomTimeTrigger、TriggerFactory。
由 QuantFramework 在初始化时通过 TriggerFactory.create_trigger() 创建对应触发器实例。
"""
import datetime


class TriggerBase:
    """触发器基类，定义触发机制的通用接口"""

    def __init__(self, framework):
        """初始化触发器

        Args:
            framework: QuantFramework 实例
        """
        self.framework = framework

    def initialize(self):
        """初始化触发器"""
        pass

    def should_trigger(self, timestamp, data):
        """判断是否应该触发策略

        Args:
            timestamp: 当前时间戳
            data:      当前市场数据

        Returns:
            bool: 是否触发策略
        """
        return False

    def get_data_period(self):
        """获取数据周期，用于数据加载

        Returns:
            str: 数据周期，如 "tick"、"1m"、"5m" 等
        """
        return "tick"


class TickTrigger(TriggerBase):
    """Tick 触发器，每个 Tick 都触发策略"""

    def should_trigger(self, timestamp, data):
        return True

    def get_data_period(self):
        return "tick"


class KLineTrigger(TriggerBase):
    """K 线触发器，在 K 线形成时触发策略"""

    def __init__(self, framework, period):
        """初始化 K 线触发器

        Args:
            framework: QuantFramework 实例
            period:    K 线周期，如 "1m"、"5m"、"1d" 等
        """
        super().__init__(framework)
        self.period = period
        self.last_trigger_time = {}   # 记录每个股票上次触发时间
        self.last_trigger_date = None  # 记录上次触发的日期（用于日 K 线）

    def should_trigger(self, timestamp, data):
        # 解析时间戳
        if isinstance(timestamp, str):
            try:
                current_time = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")
            except Exception:
                current_time = datetime.datetime.now()
        else:
            try:
                timestamp = float(timestamp)
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                current_time = datetime.datetime.fromtimestamp(timestamp)
            except Exception:
                current_time = datetime.datetime.now()

        if self.period == "1m":
            return current_time.second == 0

        elif self.period == "5m":
            return current_time.minute % 5 == 0 and current_time.second == 0

        elif self.period == "1d":
            current_date = current_time.date()
            if self.last_trigger_date != current_date:
                self.last_trigger_date = current_date
                return True
            return False

        return False

    def get_data_period(self):
        return self.period


class CustomTimeTrigger(TriggerBase):
    """自定义定时触发器，在指定的时间点触发策略"""

    def __init__(self, framework, custom_times):
        """初始化自定义定时触发器

        Args:
            framework:    QuantFramework 实例
            custom_times: 自定义触发时间点列表，格式为 ["09:30:00", "09:45:00", ...]
        """
        super().__init__(framework)
        self.trigger_seconds = []
        for time_str in custom_times:
            h, m, s = map(int, time_str.split(':'))
            self.trigger_seconds.append(h * 3600 + m * 60 + s)
        self.trigger_seconds.sort()

    def should_trigger(self, timestamp, data):
        # 解析时间戳
        if isinstance(timestamp, str):
            try:
                current_time = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")
            except Exception:
                current_time = datetime.datetime.now()
        else:
            try:
                timestamp = float(timestamp)
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                current_time = datetime.datetime.fromtimestamp(timestamp)
            except Exception:
                current_time = datetime.datetime.now()

        current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
        for trigger_second in self.trigger_seconds:
            if abs(current_seconds - trigger_second) < 5:
                return True
        return False

    def get_data_period(self):
        return "1s"


class TriggerFactory:
    """触发器工厂，用于创建不同类型的触发器"""

    @staticmethod
    def create_trigger(framework, config):
        """创建触发器

        Args:
            framework: QuantFramework 实例
            config:    配置字典

        Returns:
            TriggerBase: 触发器实例
        """
        trigger_type = config.get("backtest", {}).get("trigger", {}).get("type", "tick")

        if trigger_type == "tick":
            return TickTrigger(framework)
        elif trigger_type == "1m":
            return KLineTrigger(framework, "1m")
        elif trigger_type == "5m":
            return KLineTrigger(framework, "5m")
        elif trigger_type == "1d":
            return KLineTrigger(framework, "1d")
        elif trigger_type == "custom":
            custom_times = config.get("backtest", {}).get("trigger", {}).get("custom_times", [])
            return CustomTimeTrigger(framework, custom_times)
        else:
            return TickTrigger(framework)
