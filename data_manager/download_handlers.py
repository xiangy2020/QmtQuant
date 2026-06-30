# -*- coding: utf-8 -*-
"""
data_manager/download_handlers.py — 通用下载处理器注册机制 & 批量分层算法

设计目标：
  1. 通过处理器注册表（HANDLER_REGISTRY）将品类配置与具体下载实现解耦
  2. 新增品类时只需实现 DownloadHandler 子类并注册，无需修改框架核心逻辑
  3. build_download_plan 将 validate 结果分为三层任务，最大化利用批量接口

分层策略：
  Layer A（全量层）：has_cache == False 的标的 → 全量下载
  Layer B（缺口层）：has_cache == True 且存在 gap_segments / head_gap_segments → 按段精准下载
  Layer C（增量层）：has_cache == True 且 tail_missing > 0 → 增量下载
"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 回调接口（与 DataService 保持一致）
# ------------------------------------------------------------------

class DownloadCallbacks:
    """下载操作回调接口（可被 DataService 的 ServiceCallbacks 适配）"""

    def on_progress(self, done: int, total: int) -> None:
        """进度回调：done=已完成批次数，total=总批次数"""
        pass

    def on_log(self, message: str) -> None:
        """日志回调"""
        pass

    def on_error(self, error: str) -> None:
        """错误回调"""
        pass


# ------------------------------------------------------------------
# 处理器抽象基类
# ------------------------------------------------------------------

class DownloadHandler(ABC):
    """
    下载处理器抽象基类。

    每种子类数据（kline / calendar / instrument / sector / members）
    对应一个具体实现，框架通过 SubTypeConfig.download_handler 标识路由。
    """

    @abstractmethod
    def execute_batch(
        self,
        symbol_list: List[str],
        period: str,
        start: Optional[str],
        end: Optional[str],
        mode: str,
        callbacks: DownloadCallbacks,
    ) -> Dict:
        """
        执行一批下载任务。

        Args:
            symbol_list: 标的代码列表（批量）
            period:      数据周期，如 '1d'
            start:       起始日期（YYYYMMDD），None 表示不指定（增量模式）
            end:         结束日期（YYYYMMDD），None 表示不指定
            mode:        下载模式：'full' | 'incremental' | 'gap'
            callbacks:   回调接口

        Returns:
            {'success': bool, 'message': str, 'count': int}
        """
        ...


# ------------------------------------------------------------------
# KlineDownloadHandler：K线行情下载处理器
# ------------------------------------------------------------------

class KlineDownloadHandler(DownloadHandler):
    """
    K线行情下载处理器，内部调用 xqshare 服务端封装的 download_history_data2。

    必须使用 client.download_history_data2()（服务端封装版），
    而不是 xtdata.download_history_data2()（RPyC 透传版）。

    原因：miniQMT 的 download_history_data2 本身是异步接口，调用后立即返回，
    数据在后台异步传输。RPyC 透传版无法感知下载完成，会导致批次连续发出、
    数据实际未下载完成就进入下一批。

    服务端封装版在 Windows 本地用 threading.Event 等待 callback 触发
    finished >= total 后才返回，是真正的同步阻塞调用。
    """

    def execute_batch(
        self,
        symbol_list: List[str],
        period: str,
        start: Optional[str],
        end: Optional[str],
        mode: str,
        callbacks: DownloadCallbacks,
    ) -> Dict:
        import xqshare as _xqshare

        try:
            incrementally = (mode == 'incremental')

            callbacks.on_log(
                f"  下载 {len(symbol_list)} 只标的 [{period}]"
                f" {start or '最新'} ~ {end or '最新'}"
                f" (mode={mode})"
            )

            client = _xqshare.get_client()
            if client is None:
                raise RuntimeError("xqshare 未连接，请先调用 connect()")

            client.download_history_data2(
                stock_list=symbol_list,
                period=period,
                start_time=start or '',
                end_time=end or '',
                incrementally=incrementally,
            )
            return {'success': True, 'message': 'ok', 'count': len(symbol_list)}
        except Exception as e:
            msg = f"KlineDownloadHandler.execute_batch 失败：{e}"
            logger.error(msg, exc_info=True)
            callbacks.on_error(msg)
            return {'success': False, 'message': str(e), 'count': 0}


# ------------------------------------------------------------------
# InstrumentDownloadHandler：合约基础信息下载处理器
# ------------------------------------------------------------------

class InstrumentDownloadHandler(DownloadHandler):
    """
    合约基础信息下载处理器。

    通过 xtdata.get_instrument_detail() 逐只获取合约信息，
    并通过 save_instrument_detail() 增量合并写入 Parquet 缓存。

    注意：
      - 合约信息无"增量/缺口"概念，只支持全量刷新（mode='full'）
      - period / start / end 参数对本处理器无意义，会被忽略
      - 单只失败不中断整批，记录日志后继续处理
    """

    def execute_batch(
        self,
        symbol_list: List[str],
        period: str,
        start: Optional[str],
        end: Optional[str],
        mode: str,
        callbacks: DownloadCallbacks,
    ) -> Dict:
        from env import xtdata
        from data_manager.aux_data import save_instrument_detail as _save_detail

        if not symbol_list:
            return {'success': False, 'message': '标的列表为空', 'count': 0}

        if xtdata is None:
            msg = 'InstrumentDownloadHandler：xtdata 未初始化，请检查 xqshare 连接'
            callbacks.on_error(msg)
            return {'success': False, 'message': msg, 'count': 0}

        try:
            total = len(symbol_list)
            callbacks.on_log(f'  ▶ 获取合约基础信息，共 {total} 只...')

            detail_dict: dict = {}
            for idx, sym in enumerate(symbol_list):
                try:
                    info = xtdata.get_instrument_detail(sym)
                    if info:
                        detail_dict[sym] = {
                            'name':              str(info.get('InstrumentName', '') or ''),
                            'exchange_id':       str(info.get('ExchangeID', '') or ''),
                            'open_date':         str(info.get('OpenDate', '') or ''),
                            'expire_date':       info.get('ExpireDate', 0),
                            'pre_close':         info.get('PreClose', 0.0),
                            'up_stop_price':     info.get('UpStopPrice', 0.0),
                            'down_stop_price':   info.get('DownStopPrice', 0.0),
                            'float_volume':      info.get('FloatVolume', 0.0),
                            'total_volume':      info.get('TotalVolume', 0.0),
                            'instrument_status': info.get('InstrumentStatus', 0),
                            'is_trading':        bool(info.get('IsTrading', False)),
                            'product_type':      info.get('ProductType', -1),
                        }
                except Exception as e:
                    callbacks.on_log(f'  ✗ [{sym}] 合约信息获取失败：{e}')

                if (idx + 1) % 200 == 0 or (idx + 1) == total:
                    callbacks.on_log(f'  … 合约信息进度：{idx + 1}/{total}')
                    callbacks.on_progress(idx + 1, total)

            _save_detail(detail_dict)
            count = len(detail_dict)
            callbacks.on_log(f'  ✓ 合约基础信息已写入，共 {count} 只')
            return {'success': True, 'message': 'ok', 'count': count}

        except Exception as e:
            msg = f'InstrumentDownloadHandler.execute_batch 失败：{e}'
            logger.error(msg, exc_info=True)
            callbacks.on_error(msg)
            return {'success': False, 'message': str(e), 'count': 0}


# ------------------------------------------------------------------
# CalendarDownloadHandler：交易日历下载处理器
# ------------------------------------------------------------------

class CalendarDownloadHandler(DownloadHandler):
    """
    交易日历下载处理器。

    通过 xtdata.get_trading_dates() 获取最新交易日历，
    并通过 save_trading_calendar() 全量覆盖写入 Parquet 缓存。

    注意：
      - 交易日历无"增量/缺口"概念，只支持全量刷新（mode='full'）
      - symbol_list / period / start / end 参数对本处理器无意义，会被忽略
      - count 返回写入的交易日数量
    """

    def execute_batch(
        self,
        symbol_list: List[str],
        period: str,
        start: Optional[str],
        end: Optional[str],
        mode: str,
        callbacks: DownloadCallbacks,
    ) -> Dict:
        import datetime as _dt
        from env import xtdata
        from data_manager.aux_data import save_trading_calendar as _save_cal

        if xtdata is None:
            msg = 'CalendarDownloadHandler：xtdata 未初始化，请检查 xqshare 连接'
            callbacks.on_error(msg)
            return {'success': False, 'message': msg, 'count': 0}

        try:
            callbacks.on_log('  ▶ 获取交易日历...')
            raw_cal = xtdata.get_trading_dates('SH', start_time='19900101', end_time='')

            result: List[str] = []
            for d in (raw_cal or []):
                try:
                    s = str(int(d))
                    if len(s) in (12, 13):
                        # 12/13位均为毫秒时间戳 → 北京本地时间，禁止用 utcfromtimestamp
                        dt = _dt.datetime.fromtimestamp(int(d) / 1000)
                        result.append(dt.strftime('%Y-%m-%d'))
                    elif len(s) == 8:
                        # 8位 YYYYMMDD
                        result.append(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
                except Exception:
                    pass

            result = sorted(set(result))

            if not result:
                msg = 'CalendarDownloadHandler：交易日历返回为空'
                callbacks.on_error(msg)
                return {'success': False, 'message': msg, 'count': 0}

            _save_cal(result)
            count = len(result)
            callbacks.on_log(f'  ✓ 交易日历已写入，共 {count} 个交易日')
            callbacks.on_progress(1, 1)
            return {'success': True, 'message': 'ok', 'count': count}

        except Exception as e:
            msg = f'CalendarDownloadHandler.execute_batch 失败：{e}'
            logger.error(msg, exc_info=True)
            callbacks.on_error(msg)
            return {'success': False, 'message': str(e), 'count': 0}


# ------------------------------------------------------------------
# IndexKlineDownloadHandler：指数 K 线下载处理器
# ------------------------------------------------------------------

class IndexKlineDownloadHandler(KlineDownloadHandler):
    """
    指数 K 线下载处理器。

    复用 KlineDownloadHandler 的全部逻辑，通过继承实现。
    指数行情数据与股票行情数据使用相同的 download_history_data2 接口，
    无需额外实现，仅作为独立处理器标识注册，以便框架路由区分。
    """
    pass


# ------------------------------------------------------------------
# IndexInstrumentDownloadHandler：指数基础信息下载处理器
# ------------------------------------------------------------------

class IndexInstrumentDownloadHandler(DownloadHandler):
    """
    指数基础信息下载处理器。

    执行流程：
      1. 调用 xtdata.get_stock_list_in_sector(sector) 获取指数代码列表
      2. 逐只调用 xtdata.get_instrument_detail() 获取基础信息
      3. 保存全部字段（禁止裁剪）到 index/instrument/instrument_detail.parquet

    注意：
      - 指数基础信息无"增量/缺口"概念，只支持全量刷新（mode='full'）
      - period / start / end 参数对本处理器无意义，会被忽略
      - symbol_list 参数若非空则直接使用；若为空则通过 sector 参数获取
      - 单只失败不中断整批，记录日志后继续处理
      - 每 50 只上报一次进度
    """

    def execute_batch(
        self,
        symbol_list: List[str],
        period: str,
        start: Optional[str],
        end: Optional[str],
        mode: str,
        callbacks: DownloadCallbacks,
        sector: str = '沪深指数',
    ) -> Dict:
        from env import xtdata
        from data_manager.aux_data import save_index_instrument_detail as _save_detail

        if xtdata is None:
            msg = 'IndexInstrumentDownloadHandler：xtdata 未初始化，请检查 xqshare 连接'
            callbacks.on_error(msg)
            return {'success': False, 'message': msg, 'count': 0}

        try:
            # ── 获取指数代码列表 ──────────────────────────────────
            if not symbol_list:
                callbacks.on_log(f'  ▶ 获取 [{sector}] 指数代码列表...')
                symbol_list = xtdata.get_stock_list_in_sector(sector) or []
                if not symbol_list:
                    msg = f'IndexInstrumentDownloadHandler：板块 [{sector}] 返回空列表'
                    callbacks.on_error(msg)
                    return {'success': False, 'message': msg, 'count': 0}
                callbacks.on_log(f'  ✓ 获取到 {len(symbol_list)} 只指数代码')

            total = len(symbol_list)
            callbacks.on_log(f'  ▶ 获取指数基础信息，共 {total} 只...')

            # ── 逐只获取基础信息（保存全部字段）────────────────────
            detail_dict: dict = {}
            for idx, sym in enumerate(symbol_list):
                try:
                    info = xtdata.get_instrument_detail(sym)
                    if info:
                        # 保存 API 返回的全部字段，禁止裁剪
                        detail_dict[sym] = {k: v for k, v in info.items()}
                except Exception as e:
                    callbacks.on_log(f'  ✗ [{sym}] 指数基础信息获取失败：{e}')

                if (idx + 1) % 50 == 0 or (idx + 1) == total:
                    callbacks.on_log(f'  … 指数基础信息进度：{idx + 1}/{total}')
                    callbacks.on_progress(idx + 1, total)

            _save_detail(detail_dict)
            count = len(detail_dict)
            callbacks.on_log(f'  ✓ 指数基础信息已写入，共 {count} 只')
            return {'success': True, 'message': 'ok', 'count': count}

        except Exception as e:
            msg = f'IndexInstrumentDownloadHandler.execute_batch 失败：{e}'
            logger.error(msg, exc_info=True)
            callbacks.on_error(msg)
            return {'success': False, 'message': str(e), 'count': 0}


# ------------------------------------------------------------------
# 处理器注册表
# ------------------------------------------------------------------

HANDLER_REGISTRY: Dict[str, DownloadHandler] = {
    'kline':            KlineDownloadHandler(),
    'calendar':         CalendarDownloadHandler(),
    'instrument':       InstrumentDownloadHandler(),
    'index_kline':      IndexKlineDownloadHandler(),
    'index_instrument': IndexInstrumentDownloadHandler(),
    # 'sector':     SectorDownloadHandler(),     # 待实现
    # 'members':    MembersDownloadHandler(),    # 待实现
}


def get_handler(handler_id: str) -> Optional[DownloadHandler]:
    """按标识查找处理器，未注册返回 None"""
    return HANDLER_REGISTRY.get(handler_id)


def register_handler(handler_id: str, handler: DownloadHandler) -> None:
    """注册或覆盖处理器"""
    HANDLER_REGISTRY[handler_id] = handler


# ------------------------------------------------------------------
# DownloadPlan 数据类
# ------------------------------------------------------------------

@dataclass
class BatchTask:
    """单个批次任务"""
    symbol_list: List[str]
    period: str
    start: Optional[str]    # YYYYMMDD 或 None
    end: Optional[str]      # YYYYMMDD 或 None
    mode: str               # 'full' | 'incremental' | 'gap'
    layer: str              # 'A' | 'B' | 'C'
    desc: str = ""          # 任务描述（用于日志）


@dataclass
class DownloadPlan:
    """
    分层下载计划。

    layer_a: 全量层任务列表（无缓存标的）
    layer_b: 缺口层任务列表（按 (start, end) 分组的批次）
    layer_c: 增量层任务列表（后缺失标的）
    """
    layer_a: List[BatchTask] = field(default_factory=list)
    layer_b: List[BatchTask] = field(default_factory=list)
    layer_c: List[BatchTask] = field(default_factory=list)

    @property
    def total_batches(self) -> int:
        return len(self.layer_a) + len(self.layer_b) + len(self.layer_c)

    @property
    def layer_a_symbols(self) -> List[str]:
        symbols = []
        for t in self.layer_a:
            symbols.extend(t.symbol_list)
        return symbols

    @property
    def layer_b_symbols(self) -> List[str]:
        seen = set()
        symbols = []
        for t in self.layer_b:
            for s in t.symbol_list:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
        return symbols

    @property
    def layer_c_symbols(self) -> List[str]:
        symbols = []
        for t in self.layer_c:
            symbols.extend(t.symbol_list)
        return symbols

    def summary(self) -> str:
        """返回计划摘要字符串"""
        lines = [
            f"下载计划摘要（共 {self.total_batches} 批次）：",
            f"  Layer A（全量）：{len(self.layer_a_symbols)} 只标的，{len(self.layer_a)} 批次",
            f"  Layer B（缺口）：{len(self.layer_b_symbols)} 只标的，{len(self.layer_b)} 批次",
            f"  Layer C（增量）：{len(self.layer_c_symbols)} 只标的，{len(self.layer_c)} 批次",
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------
# build_download_plan：批量分层算法
# ------------------------------------------------------------------

def build_download_plan(
    validate_results: List[Dict],
    period: str,
    sub_type_config,
    default_start: Optional[str] = None,
) -> DownloadPlan:
    """
    将 validate 结果分层，生成结构化的下载计划。

    Args:
        validate_results:  validate_symbol 返回字典的列表
        period:            数据周期，如 '1d'
        sub_type_config:   SubTypeConfig 实例（含 download_strategy）
        default_start:     Layer A 全量下载时，若标的无 open_date 则使用此起始日期（YYYYMMDD）

    Returns:
        DownloadPlan
    """
    strategy = getattr(sub_type_config, 'download_strategy', [])
    today_str = datetime.now().strftime('%Y%m%d')
    plan = DownloadPlan()

    # ── Layer A：全量层（无缓存标的）────────────────────────────
    if 'full' in strategy:
        no_cache_symbols = [r['symbol'] for r in validate_results if not r.get('has_cache')]
        if no_cache_symbols:
            # 按 open_date 分组，相同 open_date 的合并为一批
            open_date_groups: Dict[str, List[str]] = defaultdict(list)
            for r in validate_results:
                if not r.get('has_cache'):
                    od = r.get('open_date') or ''
                    # 规范化 open_date → YYYYMMDD
                    if od and od not in ('0', '99999999', '', 'None', 'nan'):
                        od_norm = od.zfill(8)
                    else:
                        od_norm = default_start or ''
                    open_date_groups[od_norm].append(r['symbol'])

            for od_key, symbols in open_date_groups.items():
                plan.layer_a.append(BatchTask(
                    symbol_list=symbols,
                    period=period,
                    start=od_key if od_key else default_start,
                    end=today_str,
                    mode='full',
                    layer='A',
                    desc=f"全量下载 {len(symbols)} 只（起始={od_key or default_start or '未指定'}）",
                ))

    # ── Layer B：缺口层（有缓存但存在缺口的标的）────────────────
    if 'gap' in strategy:
        # 收集所有缺口段，按 (start, end) 分组
        gap_group: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for r in validate_results:
            if not r.get('has_cache'):
                continue
            all_segs: List[Tuple[str, str]] = []
            all_segs.extend(r.get('head_gap_segments', []))
            all_segs.extend(r.get('gap_segments', []))
            for seg in all_segs:
                gap_group[seg].append(r['symbol'])

        for (seg_start, seg_end), symbols in gap_group.items():
            # 去重（同一标的可能在 head_gap 和 gap 中都有同一段）
            unique_symbols = list(dict.fromkeys(symbols))
            plan.layer_b.append(BatchTask(
                symbol_list=unique_symbols,
                period=period,
                start=seg_start,
                end=seg_end,
                mode='gap',
                layer='B',
                desc=f"缺口下载 {len(unique_symbols)} 只 [{seg_start}~{seg_end}]",
            ))

    # ── Layer C：增量层（有缓存但后缺失的标的）──────────────────
    if 'incremental' in strategy:
        tail_symbols = [
            r['symbol'] for r in validate_results
            if r.get('has_cache') and r.get('tail_missing', 0) > 0
        ]
        if tail_symbols:
            plan.layer_c.append(BatchTask(
                symbol_list=tail_symbols,
                period=period,
                start=None,   # 增量模式不指定 start，由 miniQMT 自动续接
                end=None,
                mode='incremental',
                layer='C',
                desc=f"增量下载 {len(tail_symbols)} 只",
            ))

    return plan
