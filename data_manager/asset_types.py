"""
data_manager/asset_types.py — 品类体系核心定义

所有数据统一纳入品类体系管理，取代原有「行情数据 + 辅助数据」的二元划分。

品类体系结构：
    一级品类（asset_type）
    └── 二级子类（sub_type）
        └── 数据文件（Parquet）

存储路径规则：
    ~/.qmtquant/cache/{asset_type}/{sub_type}/{filename}.parquet

第一期启用：stock（股票数据）、industry（行业概念数据）
第二期启用：index（指数数据）
后续预留：etf、futures、options、bond
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import os


# ------------------------------------------------------------------
# 二级子类定义
# ------------------------------------------------------------------

@dataclass
class SubTypeConfig:
    """二级子类配置"""
    sub_type: str           # 子类标识（目录名）
    display_name: str       # 显示名称
    description: str = ""   # 描述
    # validate 字段规范（空表示不校验）
    required_fields: List[str] = field(default_factory=list)
    """该子类缓存文件必须包含的列名，validate 时动态读取"""
    field_types: Dict[str, str] = field(default_factory=dict)
    """
    各列的期望类型标识，validate 时动态读取。
    支持：'numeric' | 'date' | 'datetime' | 'timestamp' | 'string'
    """
    # smart download 能力声明
    download_strategy: List[str] = field(default_factory=list)
    """
    该子类支持的下载策略列表，smart download 框架根据此字段自动适配。
    可选値：'full' | 'incremental' | 'gap'
    空列表表示该子类暂不支持 smart 下载。
    """
    download_handler: Optional[str] = None
    """
    该子类对应的下载处理器标识，框架根据此标识路由到具体实现。
    如：'kline' | 'calendar' | 'instrument' | 'sector' | 'members'
    None 表示暂无处理器实现。
    """

# ------------------------------------------------------------------
# 一级品类定义
# ------------------------------------------------------------------

@dataclass
class AssetTypeConfig:
    """一级品类配置"""
    asset_type: str                          # 品类标识（目录名）
    display_name: str                        # 显示名称
    sub_types: List[SubTypeConfig] = field(default_factory=list)
    enabled: bool = True                     # 是否在当前期启用
    has_expiry: bool = False                 # 是否有到期日（期货/期权）
    description: str = ""                    # 描述

    def get_sub_type(self, sub_type: str) -> Optional[SubTypeConfig]:
        """按 sub_type 标识查找子类配置"""
        for st in self.sub_types:
            if st.sub_type == sub_type:
                return st
        return None

    def get_cache_path(self, sub_type: str, base_dir: str = None) -> str:
        """
        获取指定子类的缓存目录路径。

        Args:
            sub_type: 子类标识
            base_dir: 缓存根目录，默认为 ~/.qmtquant/cache

        Returns:
            str: 完整目录路径，如 ~/.qmtquant/cache/stock/kline
        """
        if base_dir is None:
            base_dir = os.path.join(os.path.expanduser("~"), ".qmtquant", "cache")
        return os.path.join(base_dir, self.asset_type, sub_type)


# ------------------------------------------------------------------
# 第一期品类注册
# ------------------------------------------------------------------

# ① 股票数据（第一期实现）
STOCK = AssetTypeConfig(
    asset_type="stock",
    display_name="股票数据",
    enabled=True,
    has_expiry=False,
    description="A股股票行情及基础信息（沪深北交所）",
    sub_types=[
        SubTypeConfig(
            sub_type="kline",
            display_name="K线行情",
            description="日线/分钟线等时序行情数据",
            required_fields=['open', 'high', 'low', 'close', 'volume'],
            field_types={
                'open':   'numeric',
                'high':   'numeric',
                'low':    'numeric',
                'close':  'numeric',
                'volume': 'numeric',
            },
            download_strategy=['full', 'incremental', 'gap'],
            download_handler='kline',
        ),
        SubTypeConfig(
            sub_type="calendar",
            display_name="交易日历",
            description="A股交易日历，原「辅助数据」归入此处",
            download_strategy=['full'],
            download_handler='calendar',
        ),
        SubTypeConfig(
            sub_type="instrument",
            display_name="合约基础信息",
            description="股票基础信息（名称、上市日期、行业等），原「辅助数据」归入此处",
            download_strategy=['full'],
            download_handler='instrument',
        ),
        SubTypeConfig(
            sub_type="moneyflow",
            display_name="资金流向",
            description="主力/大/中/小单净流入、买卖金额",
        ),
        SubTypeConfig(
            sub_type="dragonboard",
            display_name="龙虎榜",
            description="龙虎榜买卖席位及净买入金额",
        ),
        SubTypeConfig(
            sub_type="northsouth",
            display_name="北向南向资金",
            description="沪深港通资金净流入及持股数据",
        ),
        SubTypeConfig(
            sub_type="announcement",
            display_name="公告",
            description="交易所公告数据",
        ),
        SubTypeConfig(
            sub_type="financial",
            display_name="财务数据",
            description="单季度/年度财务报表（营收、利润、资产负债等）",
        ),
    ],
)

# ② 行业概念数据（第一期实现）
INDUSTRY = AssetTypeConfig(
    asset_type="industry",
    display_name="行业概念数据",
    enabled=True,
    has_expiry=False,
    description="申万行业、概念板块等成分股及板块行情",
    sub_types=[
        SubTypeConfig(
            sub_type="sector_list",
            display_name="板块分类信息",
            description="所有板块/行业名称列表（申万行业、概念板块、指数等），由 get_sector_list() 获取",
            download_strategy=['full'],
            download_handler='sector',
        ),
        SubTypeConfig(
            sub_type="members",
            display_name="成分股列表",
            description="各板块/行业的成分股列表（申万行业用 SW1xxx、概念板块用 GNxxx 等前缀）",
            download_strategy=['full'],
            download_handler='members',
        ),
    ],
)

# ③ 指数数据（第二期实现）
INDEX = AssetTypeConfig(
    asset_type="index",
    display_name="指数数据",
    enabled=True,
    has_expiry=False,
    description="上证指数、沪深300、中证500、申万行业指数等指数行情",
    sub_types=[
        SubTypeConfig(
            sub_type="kline",
            display_name="K线行情",
            description="指数日线/分钟线等时序行情数据",
            required_fields=['open', 'high', 'low', 'close', 'volume'],
            field_types={
                'open':   'numeric',
                'high':   'numeric',
                'low':    'numeric',
                'close':  'numeric',
                'volume': 'numeric',
            },
            download_strategy=['full', 'incremental', 'gap'],
            download_handler='index_kline',
        ),
        SubTypeConfig(
            sub_type="instrument",
            display_name="指数基础信息",
            description="指数名称、交易所等基础信息，通过 get_stock_list_in_sector() + get_instrument_detail() 获取",
            download_strategy=['full'],
            download_handler='index_instrument',
        ),
    ],
)

# ④ 场内基金（预留，后续实现）
ETF = AssetTypeConfig(
    asset_type="etf",
    display_name="场内基金",
    enabled=False,
    has_expiry=False,
    description="ETF/LOF等场内基金行情",
    sub_types=[
        SubTypeConfig(sub_type="kline", display_name="K线行情"),
    ],
)

# ⑤ 期货数据（预留，后续实现）
FUTURES = AssetTypeConfig(
    asset_type="futures",
    display_name="期货数据",
    enabled=False,
    has_expiry=True,
    description="商品期货、股指期货等行情及合约信息",
    sub_types=[
        SubTypeConfig(sub_type="kline", display_name="K线行情"),
        SubTypeConfig(sub_type="instrument", display_name="合约基础信息", description="到期日、标的等"),
    ],
)

# ⑥ 期权数据（预留，后续实现）
OPTIONS = AssetTypeConfig(
    asset_type="options",
    display_name="期权数据",
    enabled=False,
    has_expiry=True,
    description="ETF期权、股指期权等行情及合约信息",
    sub_types=[
        SubTypeConfig(sub_type="kline", display_name="K线行情"),
        SubTypeConfig(sub_type="instrument", display_name="合约基础信息", description="行权价、到期日、标的"),
    ],
)

# ⑦ 债券数据（预留，后续实现）
BOND = AssetTypeConfig(
    asset_type="bond",
    display_name="债券数据",
    enabled=False,
    has_expiry=False,
    description="可转债、国债等债券行情",
    sub_types=[
        SubTypeConfig(sub_type="kline", display_name="K线行情"),
    ],
)


# ------------------------------------------------------------------
# 全局品类注册表
# ------------------------------------------------------------------

# 所有品类（按顺序，第一期启用的在前）
ALL_ASSET_TYPES: List[AssetTypeConfig] = [
    STOCK,
    INDUSTRY,
    INDEX,
    ETF,
    FUTURES,
    OPTIONS,
    BOND,
]

# 仅第一期启用的品类
ENABLED_ASSET_TYPES: List[AssetTypeConfig] = [
    at for at in ALL_ASSET_TYPES if at.enabled
]

# 按 asset_type 标识快速查找
_ASSET_TYPE_MAP = {at.asset_type: at for at in ALL_ASSET_TYPES}


def get_asset_type(asset_type: str) -> Optional[AssetTypeConfig]:
    """按标识查找品类配置，未找到返回 None"""
    return _ASSET_TYPE_MAP.get(asset_type)


def get_cache_path(asset_type: str, sub_type: str, base_dir: str = None) -> str:
    """
    获取指定品类/子类的缓存目录路径。

    Args:
        asset_type: 一级品类标识，如 'stock'
        sub_type:   二级子类标识，如 'kline'
        base_dir:   缓存根目录，默认 ~/.qmtquant/cache

    Returns:
        str: 完整目录路径

    Raises:
        ValueError: 品类标识不存在时抛出
    """
    at = get_asset_type(asset_type)
    if at is None:
        raise ValueError(f"未知品类标识：{asset_type!r}，可用值：{list(_ASSET_TYPE_MAP.keys())}")
    return at.get_cache_path(sub_type, base_dir)
