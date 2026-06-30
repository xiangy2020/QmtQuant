# -*- coding: utf-8 -*-
"""
data_api/server.py — FastAPI 应用实例、路由注册、中间件

职责：
  - 创建 FastAPI 应用实例
  - 注册全局异常处理器（500 不暴露堆栈）
  - 添加响应头中间件（注入 X-QmtQuant-Version）
  - 注册所有路由（/health + /api/v1/*）
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# 版本号（与项目保持一致）
API_VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────────────
# 统一响应模型
# ──────────────────────────────────────────────────────────────────

def ok(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应体"""
    return {"code": 0, "message": message, "data": data}


def err(message: str, code: int = 1, data: Any = None) -> dict:
    """构造错误响应体"""
    return {"code": code, "message": message, "data": data}


def ok_response(data: Any = None, message: str = "ok", status_code: int = 200) -> JSONResponse:
    """返回成功 JSONResponse"""
    return JSONResponse(content=ok(data, message), status_code=status_code)


def err_response(message: str, code: int = 1, status_code: int = 200, data: Any = None) -> JSONResponse:
    """返回错误 JSONResponse"""
    return JSONResponse(content=err(message, code, data), status_code=status_code)


# ──────────────────────────────────────────────────────────────────
# 响应头中间件：注入 X-QmtQuant-Version
# ──────────────────────────────────────────────────────────────────

class VersionHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-QmtQuant-Version"] = API_VERSION
        return response


# ──────────────────────────────────────────────────────────────────
# FastAPI 应用工厂
# ──────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。

    Returns:
        配置好路由、中间件、异常处理器的 FastAPI 实例
    """
    app = FastAPI(
        title="QmtQuant Data API",
        description="QmtQuant 本地数据 HTTP 服务，提供 K 线、板块、合约、日历等数据查询接口",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── 中间件 ─────────────────────────────────────────────────────
    app.add_middleware(VersionHeaderMiddleware)

    # ── 全局异常处理器（500 不暴露堆栈）──────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"未捕获异常 [{request.method} {request.url.path}]: {exc}",
            exc_info=True,
        )
        # 仅返回摘要，不暴露完整堆栈
        summary = f"{type(exc).__name__}: {str(exc)[:200]}"
        return JSONResponse(
            content=err(f"服务内部错误：{summary}", code=500),
            status_code=500,
            headers={"X-QmtQuant-Version": API_VERSION},
        )

    # ── 注册路由 ───────────────────────────────────────────────────
    from data_api.handlers import router
    app.include_router(router)

    return app
