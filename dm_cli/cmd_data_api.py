# -*- coding: utf-8 -*-
"""
dm_cli/cmd_data_api.py — data-api 子命令实现

启动 QmtQuant HTTP API 服务（FastAPI + uvicorn），
将本地 Parquet 缓存数据对外暴露为 REST 接口。
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

from dm_cli.common import _info, _err, _warn


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def _is_port_in_use(host: str, port: int) -> bool:
    """检测端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def _print_cache_status() -> None:
    """打印缓存目录状态（各数据目录文件数量）"""
    cache_root = Path.home() / ".qmtquant" / "cache"
    _info(f"缓存根目录：{cache_root}")

    dirs_to_check = [
        ("stock/kline/1d",              "股票日线 K 线"),
        ("stock/kline/1m",              "股票分钟 K 线"),
        ("stock/instrument",            "股票合约信息"),
        ("stock/calendar",              "交易日历"),
        ("industry/members",            "行业板块成分股"),
        ("industry/sector_list",        "板块列表"),
    ]

    for rel_path, label in dirs_to_check:
        full_path = cache_root / rel_path
        if full_path.exists():
            count = sum(1 for _ in full_path.rglob("*.parquet"))
            _info(f"  {label:<16} {rel_path:<30} {count} 个文件")
        else:
            _warn(f"  {label:<16} {rel_path:<30} 目录不存在")


def _print_routes() -> None:
    """打印已注册的接口列表"""
    routes = [
        ("GET", "/health",              "健康检查"),
        ("GET", "/api/v1/kline",        "K 线数据查询"),
        ("GET", "/api/v1/sector",       "板块成分股查询"),
        ("GET", "/api/v1/instruments",  "合约基础信息查询"),
        ("GET", "/api/v1/calendar",     "交易日历查询"),
        ("GET", "/docs",                "Swagger UI 文档"),
    ]
    _info("已注册接口：")
    for method, path, desc in routes:
        _info(f"  {method:<6} {path:<30} {desc}")


# ──────────────────────────────────────────────────────────────────
# 子命令主函数
# ──────────────────────────────────────────────────────────────────

def cmd_data_api(args) -> None:
    """
    启动 QmtQuant HTTP API 服务。

    参数优先级：命令行 > .env 环境变量 > 默认值

    Args:
        args: argparse.Namespace，包含 host、port 参数（均可为 None 表示未显式传入）
    """
    import os

    # ── 检查 XQSHARE_REMOTE_HOST 是否已配置 ───────────────────────
    xqshare_host = os.environ.get("XQSHARE_REMOTE_HOST", "").strip()
    if not xqshare_host:
        _err("未配置 XQSHARE_REMOTE_HOST，无法连接 xqshare server。")
        _err("请在项目根目录的 .env 文件中添加：")
        _err("  XQSHARE_REMOTE_HOST=127.0.0.1        # Windows 本机")
        _err("  XQSHARE_REMOTE_HOST=192.168.x.x      # Linux 远程连接 Windows")
        sys.exit(1)

    # ── 解析 host/port（命令行 > 环境变量 > 默认值）────────────────
    host = args.host or os.environ.get("DATA_API_HOST", "").strip() or "127.0.0.1"
    if args.port is not None:
        port = args.port
    else:
        env_port = os.environ.get("DATA_API_PORT", "").strip()
        port = int(env_port) if env_port else 8765

    # ── 检测端口占用 ───────────────────────────────────────────────
    if _is_port_in_use(host, port):
        _err(f"端口 {port} 已被占用，请更换端口或停止占用该端口的进程")
        _err(f"  可尝试：python dm_cli.py data-api --port {port + 1}")
        sys.exit(1)

    # ── 打印启动信息 ───────────────────────────────────────────────
    _info("=" * 60)
    _info("QmtQuant Data API 服务启动中...")
    _info(f"服务地址：http://{host}:{port}")
    _info(f"API 文档：http://{host}:{port}/docs")
    _info("=" * 60)

    _print_cache_status()
    print()
    _print_routes()
    print()
    _info("按 Ctrl+C 停止服务")
    _info("=" * 60)

    # ── 启动 uvicorn ───────────────────────────────────────────────
    try:
        import uvicorn
        from data_api.server import create_app

        app = create_app()
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    except ImportError as e:
        _err(f"缺少依赖：{e}")
        _err("请执行：pip install fastapi uvicorn[standard]")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        _info("服务已停止")
