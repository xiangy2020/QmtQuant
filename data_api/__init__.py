# -*- coding: utf-8 -*-
"""
data_api — QmtQuant HTTP API 服务模块

提供基于 FastAPI 的 REST 接口，将本地 Parquet 缓存数据对外暴露，
供 daily_stock_analysis 等外部项目通过 HTTP 调用。

模块结构：
    server.py   — FastAPI 应用实例 + 路由注册 + 中间件
    handlers.py — 各接口的业务处理逻辑
    client.py   — 客户端 SDK（供其他项目复制使用）

启动方式：
    python dm_cli.py data-api --port 8765
"""

from data_api.server import create_app

__all__ = ["create_app"]
