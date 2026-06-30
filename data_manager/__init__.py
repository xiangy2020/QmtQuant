"""
data_manager - 项目数据管理模块

提供本地 Parquet 缓存的存储、同步、查询和生命周期管理功能。

数据流架构（新）：
  [miniQMT 本地缓存]
        ↓（SyncPipeline: MiniQMTSource → ParquetSink）
  ~/.qmtquant/cache/{asset_type}/{sub_type}/
        ↓（日常使用）
  DataService.query_kline() → 策略/回测/查看器直接读取（毫秒级）

品类体系：
  stock/kline/{period}/{market}/{code}.parquet
  stock/calendar/trading_calendar.parquet
  stock/instrument/instrument_detail.parquet
  stock/kline/sync_meta.parquet
  stock/sector_list.parquet
  industry/members/{sector_name}.parquet
"""

# 依赖检测：pyarrow 是核心依赖，缺失时给出明确提示
try:
    import pyarrow  # noqa: F401
except ImportError:
    raise ImportError(
        "\n[data_manager] 缺少必要依赖 pyarrow。\n"
        "请执行以下命令安装：\n"
        "    pip install pyarrow>=12.0\n"
    )

# 品类体系
from .asset_types import (
    AssetTypeConfig,
    SubTypeConfig,
    STOCK,
    INDUSTRY,
    ALL_ASSET_TYPES,
    ENABLED_ASSET_TYPES,
    get_asset_type,
    get_cache_path,
)

# 存储引擎
from .storage import Storage, save_parquet, load_parquet, parquet_exists

# 同步管理器（新接口）
from .sync_manager import save_kline, get_sync_status, get_all_sync_meta

# 数据同步框架
from .sync_pipeline import (
    SyncSource,
    SyncSink,
    MiniQMTSource,
    ParquetSink,
    SyncPipeline,
)

# 缓存生命周期管理
from .cache_manager import get_statistics, validate_cache, clear_all

# 数据完整性检测
from .data_integrity import (
    get_cached_dates,
    get_date_range,
    calc_gap_segments,
    scan_symbol_gaps,
    batch_scan_gaps,
)

# 辅助数据（交易日历 + 合约基础信息）本地持久化
from .aux_data import (
    save_trading_calendar,
    load_trading_calendar,
    save_instrument_detail,
    load_instrument_detail,
)

__all__ = [
    # 品类体系
    "AssetTypeConfig",
    "SubTypeConfig",
    "STOCK",
    "INDUSTRY",
    "ALL_ASSET_TYPES",
    "ENABLED_ASSET_TYPES",
    "get_asset_type",
    "get_cache_path",
    # 存储引擎
    "Storage",
    "save_parquet",
    "load_parquet",
    "parquet_exists",
    # 同步管理器
    "save_kline",
    "get_sync_status",
    "get_all_sync_meta",
    # 数据同步框架
    "SyncSource",
    "SyncSink",
    "MiniQMTSource",
    "ParquetSink",
    "SyncPipeline",
    # 缓存管理
    "get_statistics",
    "validate_cache",
    "clear_all",
    # 数据完整性检测
    "get_cached_dates",
    "get_date_range",
    "calc_gap_segments",
    "scan_symbol_gaps",
    "batch_scan_gaps",
    # 辅助数据（交易日历 + 合约基础信息）
    "save_trading_calendar",
    "load_trading_calendar",
    "save_instrument_detail",
    "load_instrument_detail",
]

__version__ = "2.0.0"
