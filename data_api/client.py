# -*- coding: utf-8 -*-
"""
data_api/client.py — QmtQuant Data API 客户端 SDK

使用方式（其他项目复制此文件后直接使用）：

    from client import QmtQuantClient

    client = QmtQuantClient(host="localhost", port=8765)

    # 查询 K 线（返回 DataFrame，字段与 daily_stock_analysis STANDARD_COLUMNS 一致）
    df = client.get_kline("600519.SH", "1d", "20240101", "20241231")

    # 查询板块成分股（返回 [[symbol, name], ...]，与 DataFetcherManager.get_sector() 兼容）
    members = client.get_sector("沪深300")

    # 查询合约基础信息（返回 {symbol: {...}} 字典）
    instruments = client.get_instruments(["600519.SH", "000001.SZ"])

    # 查询交易日历（返回 ['YYYY-MM-DD', ...] 列表）
    calendar = client.get_calendar("20240101", "20241231")

依赖：
    - requests（标准库外，需 pip install requests）
    - pandas（需 pip install pandas）

异常：
    - QmtQuantConnectionError：服务不可达（连接超时/拒绝）
    - QmtQuantAPIError：服务返回非 0 code 的业务错误
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# 自定义异常
# ──────────────────────────────────────────────────────────────────

class QmtQuantConnectionError(Exception):
    """服务不可达（连接超时/拒绝）"""
    pass


class QmtQuantAPIError(Exception):
    """服务返回业务错误（code != 0）"""
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


# ──────────────────────────────────────────────────────────────────
# 客户端主类
# ──────────────────────────────────────────────────────────────────

class QmtQuantClient:
    """
    QmtQuant Data API 客户端。

    Args:
        host:    服务地址，默认 "localhost"
        port:    服务端口，默认 8765
        timeout: 请求超时秒数，默认 10
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        timeout: float = 10.0,
    ):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    # ── 内部工具方法 ───────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """
        发起 GET 请求，返回响应体 dict。

        Raises:
            QmtQuantConnectionError: 连接失败
            QmtQuantAPIError: 服务返回 code != 0
        """
        try:
            import requests
        except ImportError:
            raise ImportError("请先安装 requests：pip install requests")

        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            raise QmtQuantConnectionError(
                f"无法连接到 QmtQuant API 服务 {self.base_url}，请确认服务已启动：{e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise QmtQuantConnectionError(
                f"连接 QmtQuant API 服务超时（{self.timeout}s）：{e}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise QmtQuantConnectionError(f"请求失败：{e}") from e

    def _check_response(self, resp: dict) -> any:
        """检查响应 code，非 0 时抛出 QmtQuantAPIError，返回 data 字段"""
        code = resp.get("code", -1)
        message = resp.get("message", "未知错误")
        if code != 0:
            raise QmtQuantAPIError(message, code)
        return resp.get("data")

    # ── 公共接口 ───────────────────────────────────────────────────

    def health(self) -> dict:
        """
        健康检查。

        Returns:
            包含 status/version/cache_stats 的字典
        """
        resp = self._get("/health")
        return self._check_response(resp)

    def get_kline(
        self,
        symbol: str,
        period: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        format: str = "standard",
    ):
        """
        查询 K 线数据。

        Args:
            symbol: 股票代码，如 "600519.SH"
            period: 数据周期，如 "1d"、"1m"
            start:  起始日期，格式 YYYYMMDD 或 YYYY-MM-DD
            end:    结束日期，格式 YYYYMMDD 或 YYYY-MM-DD
            format: "standard"（默认，STANDARD_COLUMNS）或 "raw"（原始字段）

        Returns:
            pd.DataFrame，字段为 date/open/high/low/close/volume/amount/pct_chg
            （format=standard 时），或原始字段（format=raw 时）

        Raises:
            QmtQuantConnectionError: 服务不可达
            QmtQuantAPIError: 服务返回业务错误
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("请先安装 pandas：pip install pandas")

        params = {"symbol": symbol, "period": period, "format": format}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        resp = self._get("/api/v1/kline", params=params)
        data = self._check_response(resp)

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df

    def get_sector(self, name: Optional[str] = None) -> Union[List[List], List[str]]:
        """
        查询板块成分股。

        Args:
            name: 板块名称，如 "沪深300"；不传则返回所有板块名称列表

        Returns:
            - 带 name：[[symbol, sector_name], ...] 格式（与 DataFetcherManager.get_sector() 兼容）
            - 不带 name：板块名称字符串列表 ['沪深300', '上证50', ...]

        Raises:
            QmtQuantConnectionError: 服务不可达
            QmtQuantAPIError: 服务返回业务错误
        """
        params = {}
        if name:
            params["name"] = name

        resp = self._get("/api/v1/sector", params=params)
        data = self._check_response(resp)

        if not data:
            return []

        if name:
            # 转换为 [[symbol, name], ...] 格式（与 DataFetcherManager.get_sector() 兼容）
            result = []
            for item in data:
                if isinstance(item, dict):
                    result.append([item.get("symbol", ""), item.get("name", "")])
                else:
                    result.append(item)
            return result
        else:
            # 返回板块名称列表
            return data

    def get_instruments(
        self,
        symbols: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 500,
    ) -> Dict[str, dict]:
        """
        查询合约基础信息。

        Args:
            symbols:   股票代码列表，如 ["600519.SH", "000001.SZ"]；不传则返回全量（分页）
            page:      页码（全量模式有效）
            page_size: 每页数量（全量模式有效）

        Returns:
            以 symbol 为 key 的字典，如 {"600519.SH": {"name": "贵州茅台", ...}}

        Raises:
            QmtQuantConnectionError: 服务不可达
            QmtQuantAPIError: 服务返回业务错误（如依赖文件缺失时 503）
        """
        params: dict = {"page": page, "page_size": page_size}
        if symbols:
            params["symbols"] = ",".join(symbols)

        resp = self._get("/api/v1/instruments", params=params)
        data = self._check_response(resp)

        if not data:
            return {}

        # 全量模式返回 {total, items, ...}，批量查询返回列表
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            return {}

        return {item["symbol"]: {k: v for k, v in item.items() if k != "symbol"} for item in items if "symbol" in item}

    def get_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[str]:
        """
        查询交易日历。

        Args:
            start: 起始日期，格式 YYYYMMDD 或 YYYY-MM-DD
            end:   结束日期，格式 YYYYMMDD 或 YYYY-MM-DD

        Returns:
            交易日列表，格式 ['YYYY-MM-DD', ...]

        Raises:
            QmtQuantConnectionError: 服务不可达
            QmtQuantAPIError: 服务返回业务错误（如依赖文件缺失时 503）
        """
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        resp = self._get("/api/v1/calendar", params=params)
        return self._check_response(resp) or []
