---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: always
---
# 架构专项规范

> 适用场景：文件超过行数限制需要重构、新功能设计、涉及分层架构调整时加载本文件。

---

## 一、大文件重构规范（强制）

### 1.1 触发条件

| 触发条件 | 强制动作 |
|---------|---------|
| 单个 `.py` 文件超过 **2000 行** | 禁止在该文件继续追加新功能，必须先提出拆分方案，经用户确认后再动手 |
| 单个 `class` 超过 **1000 行** | 必须评估是否可用 Mixin 或子类拆分，给出方案后再写代码 |
| 单个函数/方法超过 **100 行** | 必须拆分为多个子函数，不允许以"逻辑连贯"为由保留超长函数 |
| 新增功能会导致文件**从2000行以下突破2000行** | 必须先停下来，提示用户该文件即将超限，给出拆分建议后再继续 |

### 1.2 拆分方向优先级

**优先级1：按职责分层**

```
LargeModule.py (超大文件)
├── module/main.py        # 主框架、布局
├── module/events.py      # 事件处理
├── module/actions.py     # 业务动作、业务逻辑
└── module/state.py       # 状态管理、配置持久化
```

**优先级2：按功能域拆分（适用于数据处理/分析类）**

```
DataProcessor.py
├── processor/base.py     # 基类
├── processor/kline.py    # K线处理
├── processor/tick.py     # Tick数据处理
└── processor/factor.py   # 因子处理
```

**优先级3：Mixin 模式（适用于单个 class 过大但文件整体不大）**

```python
# 将横切关注点抽成 Mixin，主类保持精简
class DataService(ValidationMixin, ExportMixin, ConfigMixin):
    pass
```

**优先级4：工具/组件下沉（适用于工具集文件）**

```
Tools.py
├── widgets/table.py    # 表格相关组件
├── widgets/chart.py    # 图表相关组件
└── utils/common.py     # 纯工具函数
```

---

### 1.3 拆分后文件放置规范（强制）

**核心原则：拆分产物必须放入合适的目录，禁止将拆分出的子文件散落在原文件所在目录（尤其是项目根目录）。**

#### 强制规则

| 场景 | 强制动作 |
|------|---------|
| 拆分后产生 **2 个及以上**子文件 | 必须创建专属目录收纳，禁止平铺在原目录 |
| 原文件位于**项目根目录** | 拆分产物必须移入子目录，原文件可保留为入口文件（仅做 import 转发）或一并移入 |
| 拆分产物与原文件**同属一个功能域** | 统一放入以原文件名（去掉 `.py`）命名的目录，或放入已有的同功能目录 |
| 拆分产物**跨越多个功能域** | 按功能域分别放入对应目录，不强制合并到同一目录 |

#### 目录命名规范

- 目录名使用**小写下划线**（`snake_case`），与 Python 包命名规范一致
- 目录内必须包含 `__init__.py`，使其成为合法的 Python 包
- `__init__.py` 中应导出该包的公共接口，方便外部调用

#### 典型示例

**❌ 禁止：拆分后平铺在根目录**
```
/                              ← 项目根目录
├── LargeModule.py             ← 原文件（已超限）
├── LargeModule_main.py        ← 拆分产物，禁止放这里
├── LargeModule_events.py      ← 拆分产物，禁止放这里
├── LargeModule_actions.py     ← 拆分产物，禁止放这里
└── LargeModule_state.py       ← 拆分产物，禁止放这里
```

**✅ 正确：创建目录收纳**
```
/                              ← 项目根目录
├── LargeModule.py             ← 入口文件（仅做 import 转发，保持向后兼容）
└── large_module/              ← 专属目录
    ├── __init__.py            ← 导出公共接口
    ├── main.py                ← 主框架、布局
    ├── events.py              ← 事件处理
    ├── actions.py             ← 业务逻辑
    └── state.py               ← 状态管理、配置持久化
```

**✅ 正确：功能域已有目录时直接放入**
```
/
├── data_manager/           ← 已有目录
│   ├── __init__.py
│   ├── storage.py
│   ├── data_integrity.py      ← 从根目录拆分后放入已有目录
│   └── download_handlers.py ← 从根目录拆分后放入已有目录
```

#### 入口文件转发模板

当原文件需要保留（维持向后兼容的 import 路径）时，原文件改写为纯转发：

```python
# LargeModule.py（入口转发文件，保持向后兼容）
# 实际实现已移至 large_module/ 目录
from large_module import LargeModule  # noqa: F401
```

---

## 二、分层架构总纲（强制）

### 2.1 核心原则

**后端逻辑优先**：
```
所有业务逻辑 = 纯 Python 类/函数，不依赖任何外部UI框架
对外通信 = 通过回调传递进度和结果
```

### 2.2 两层架构模型

```
┌─────────────────────────────────────────────────────┐
│  Layer 2: 后端服务层（纯 Python）                    │
│  DataService / BacktestService / StrategyService     │
│  统一接口：run(params, callbacks) → result           │
│  callbacks = {on_progress, on_log, on_error}         │
│  对外入口：CLI（dm_cli / bt_cli）                    │
├─────────────────────────────────────────────────────┤
│  Layer 1: 核心引擎                                   │
│  data_manager / framework / strategy / utils         │
└─────────────────────────────────────────────────────┘
```

CLI 入口文件：
- `dm_cli.py` → 数据管理命令行入口
- `bt_cli.py` → 回测命令行入口

### 2.3 后端服务层规范

#### 服务类命名与职责

| 服务类 | 职责 | 对应 Layer 1 模块 |
|--------|------|------------------|
| `DataService` | 数据管理服务 | `data_manager` |
| `BacktestService` | 回测服务 | `framework_backtest_mixin` |
| `StrategyService` | 策略服务 | `framework` |
| `TradeService` | 交易服务 | `Trade` |

#### 统一回调接口

所有后端服务必须实现以下回调接口：

```python
class ServiceCallbacks:
    def on_progress(self, done: int, total: int) -> None:
        """进度回调：done=已完成数量，total=总数量"""
        pass

    def on_log(self, message: str) -> None:
        """日志回调"""
        pass

    def on_error(self, error: str) -> None:
        """错误回调"""
        pass

    def on_done(self, result: dict) -> None:
        """完成回调"""
        pass
```

#### 服务方法签名规范

`DataService` 实现文件：`data_service.py`

```python
class DataService:
    # ── 数据下载（全量 / 增量 / 缺口）────────────────────────
    def download(
        self,
        params: dict,
        callbacks: ServiceCallbacks,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        数据下载服务，支持三种模式（通过 params['mode'] 指定）：

          - full（全量）：强制重新下载指定日期范围内的全部数据
          - incremental（增量）：从 miniQMT 本地最后一条数据往后补充（默认）
          - gap（缺口）：扫描 Parquet 缓存缺口，逐段精准补充

        params 字段：
            stock_list:   list[str]  股票代码列表（必填）
            period_type:  str        数据周期，如 '1d'（必填）
            mode:         str        补充模式：'full' | 'incremental' | 'gap'
                                     默认 'incremental'
            asset_type:   str        一级品类，默认 'stock'（预留扩展）
            sub_type:     str        二级子类，默认 'kline'（预留扩展）

            # full / incremental 模式专用：
            start_date:   str        起始日期 YYYYMMDD（full 模式必填；incremental 留空）
            end_date:     str        结束日期 YYYYMMDD（可选，默认最新）

        返回（full / incremental 模式）：
            {'success': bool, 'message': str, 'mode': str}

        返回（gap 模式）：
            {
                'success': bool, 'message': str, 'mode': 'gap',
                'interrupted': bool,
                'processed': int,       # 有缓存且参与缺口计算的股票数
                'has_gap': int,         # 有缺口的股票数
                'no_gap': int,          # 无缺口的股票数
                'no_cache': int,        # 无缓存跳过的股票数
                'total_segments': int,
                'done_segments': int,
            }

        内部实现：
          - full / incremental → _download_download()，调用 xtdata.download_history_data2
          - gap → _download_gap()，扫描 Parquet 缺口后逐段调用 xtdata.download_history_data2
        """

    # ── 缺口补充（向后兼容别名）────────────────────────────────
    def gap_download(
        self,
        params: dict,           # stock_list, period_type
        callbacks: ServiceCallbacks,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        缺口补充服务（向后兼容别名）。

        内部直接调用 download(mode='gap', ...)，返回值与 download gap 模式相同。
        新代码请直接使用 download(params={'mode': 'gap', ...})。
        """

    # ── 数据同步（miniQMT → Parquet）──────────────────────────
    def sync(
        self,
        params: dict,           # symbols, periods, start_date, end_date
        callbacks: ServiceCallbacks,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """通过 SyncPipeline(MiniQMTSource → ParquetSink) 同步 K 线数据"""

    # ── 辅助数据同步（交易日历 + 合约信息）────────────────────
    def sync_aux_data(
        self,
        symbol_list: list = None,
        callbacks: ServiceCallbacks = None,
    ) -> dict:
        """
        同步交易日历和合约基础信息到 Parquet 缓存。

        存储路径：
          ~/.qmtquant/cache/stock/calendar/trading_calendar.parquet
          ~/.qmtquant/cache/stock/instrument/instrument_detail.parquet

        合约信息保存字段（来源：xtdata.get_instrument_detail()）：
            name              str    合约名称（InstrumentName）
            exchange_id       str    交易所代码（ExchangeID，如 SZ/SH）
            open_date         str    上市日期（OpenDate，格式 YYYYMMDD；特殊值见 API 文档）
            expire_date       int    退市日/到期日（ExpireDate；0 或 99999999 表示无退市日）
            pre_close         float  前收盘价（PreClose）
            up_stop_price     float  当日涨停价（UpStopPrice）
            down_stop_price   float  当日跌停价（DownStopPrice）
            float_volume      float  流通股本，单位：股（FloatVolume）
            total_volume      float  总股本，单位：股（TotalVolume）
            instrument_status int    停牌状态（InstrumentStatus；<=0 正常，>=1 停牌天数）
            is_trading        bool   是否可交易（IsTrading）
            product_type      int    合约类型（ProductType；股票默认 -1）

        返回：
            {
                'calendar_ok':    bool,  # 交易日历是否同步成功
                'detail_ok':      bool,  # 合约信息是否同步成功
                'detail_count':   int,   # 成功同步的合约数量
            }

        注意事项：
          - 合约信息采用增量合并写入，新数据覆盖同 symbol 旧数据，不删除其他 symbol
          - 禁止在同步阶段裁剪字段，必须保存 API 返回的全部字段
        """

    # ── 行业概念数据同步（板块列表 + 成分股）──────────────────
    def sync_industry_data(
        self,
        params: dict,           # sectors（可选）: list[str]，指定板块名称列表；不传则全量同步
        callbacks: ServiceCallbacks = None,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        同步行业概念数据到 Parquet 缓存（industry/sector_list + industry/members/）。

        执行顺序：
          1. 调用 xtdata.download_sector_data() 下载板块分类信息（触发 miniQMT 本地缓存更新）
          2. 同步 sector_list → industry/sector_list/sector_list.parquet
          3. 逐板块同步 members → industry/members/{sector_name}.parquet

        params 字段：
            sectors: list[str]（可选）指定板块名称列表，不传则同步全量板块

        返回：
            {
                'success':         bool,   # 整体是否成功（未中断且无异常）
                'sector_list_ok':  bool,   # sector_list 是否写入成功
                'members_success': int,    # 成功写入的板块成分股数量
                'members_failed':  int,    # 写入失败的板块数量
                'total_sectors':   int,    # 本次处理的板块总数
                'interrupted':     bool,   # 是否被 stop_flag 中断
            }

        注意事项：
          - sector_kline（板块行情）暂未实现，留待后续
          - 板块名称文件名中的特殊字符（/、\\、空格）会被替换为 _
          - 进度以板块数为单位上报（on_progress(done, total)）
        """

    # ── 全面数据健康检查 ──────────────────────────────────────
    def validate_kline(
        self,
        params: dict,
        callbacks: ServiceCallbacks = None,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        对股票池执行全面数据健康检查（stock/kline）。

        执行顺序：
          1. 依赖链检查：calendar + instrument 文件是否存在
          2. 加载交易日历（复用 _fetch_trading_dates_sorted()）和合约信息
          3. 调用 batch_validate 批量校验
          4. 汇总结果

        params 字段：
            stock_list:       list[str]      股票代码列表（必填）
            period:           str            数据周期，如 '1d'（必填）
            sub_type_config:  SubTypeConfig  子类配置实例（含 required_fields / field_types）（必填）

        校验维度（由 data_integrity.validate_symbol 执行）：
          1. 字段完整度：required_fields 是否全部存在
          2. 字段类型一致性：field_types 中各列是否符合期望类型；索引是否为 DatetimeIndex
          3. 前缺失：缓存起始日期 vs 上市日期（open_date）+ 5 个交易日容差
          4. 后缺失：缓存最新日期 vs 最近一个交易日

        返回：
            {
                'success':        bool,   # 整体是否成功（未中断且无异常）
                'total':          int,    # 总扫描数
                'no_cache':       int,    # 无缓存数
                'field_error':    int,    # 字段不完整数
                'type_error':     int,    # 类型异常数
                'head_missing':   int,    # 前缺失数
                'tail_missing':   int,    # 后缺失数
                'healthy':        int,    # 完全健康数
                'interrupted':    bool,
                'results':        list,   # 每只股票的 validate_symbol 结果字典列表
            }

        results 列表中每个字典的字段（validate_symbol 返回结构）：
            symbol:            str               股票代码
            has_cache:         bool              是否有本地缓存
            field_ok:          bool              字段完整度是否通过
            type_ok:           bool              字段类型是否通过
            missing_fields:    list[str]         缺失的必要字段列表
            type_errors:       list[dict]        类型异常列表（含 col/expected/actual）
            head_missing:      int               前缺失交易日数
            tail_missing:      int               后缺失交易日数
            cache_start:       str|None          缓存起始日期（'YYYY-MM-DD'）
            cache_end:         str|None          缓存最新日期（'YYYY-MM-DD'）
            open_date:         str|None          上市日期（'YYYYMMDD'）
            gap_segments:      list[tuple]       缓存范围内的中间缺口段 [('YYYYMMDD','YYYYMMDD'),...]
            head_gap_segments: list[tuple]       上市日期到缓存起始之间的缺失段
            tail_start:        str|None          后缺失的起始补充日期（'YYYYMMDD'）

        注意事项：
          - calendar 或 instrument 文件缺失时通过 on_error 报错并提前返回
          - 前缺失容差为 5 个交易日（上市初期数据不完整属正常情况）
          - gap_segments / head_gap_segments / tail_start 供 smart_download 直接消费，无需重复扫描
        """

    # ── 智能补充（smart download）──────────────────────────
    def smart_download(
        self,
        validate_result: dict,
        params: dict,
        callbacks: ServiceCallbacks = None,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        基于 validate 结果执行通用精准数据修复（smart download）。

        直接消费 validate_kline 的扫描结果，按问题类型分层选择补充策略，
        避免重复扫描。支持任意品类，通过 SubTypeConfig.download_handler 路由。

        分层策略：
          Layer A（全量层）：has_cache == False 的标的 → 全量补充
          Layer B（缺口层）：has_cache == True 且存在 gap_segments / head_gap_segments → 按段精准补充
          Layer C（增量层）：has_cache == True 且 tail_missing > 0 → 增量补充

        批量优化：
          - Layer A：所有无缓存标的按 open_date 分组，相同 open_date 合并为一次批量调用
          - Layer B：按 (start, end) 分组，相同区间的标的合并为一次批量调用
          - Layer C：所有后缺失标的合并为一次批量调用（incrementally=True）

        params 字段：
            asset_type:    str  一级品类，如 'stock'（必填）
            sub_type:      str  二级子类，如 'kline'（必填）
            period:        str  数据周期，如 '1d'（必填）
            default_start: str  全量补充时无 open_date 的标的使用此起始日期（YYYYMMDD，可选）

        返回：
            {
                'success':          bool,  # 未中断且无失败批次
                'total_batches':    int,   # 总批次数
                'done_batches':     int,   # 已执行批次数
                'failed_batches':   int,   # 失败批次数
                'download_count': int,   # 补充标的数（去重）
                'skipped_count':    int,   # 跳过标的数
                'interrupted':      bool,
                'layer_a_count':    int,   # Layer A 补充标的数
                'layer_b_count':    int,   # Layer B 补充标的数
                'layer_c_count':    int,   # Layer C 补充标的数
            }

        注意事项：
          - 必须先调用 validate_kline 获取 validate_result，再传入此方法
          - validate_result 在内存中传递，不写入磁盘
          - 若 SubTypeConfig.download_handler 未注册，通过 on_log 提示并返回
          - 若 download_strategy 为空，跳过并返回
          - 某批次失败不中断整体流程，记录失败信息后继续下一批次
        """

    # ── 智能同步（smart sync）────────────────────────────────
    def sync_smart(
        self,
        validate_result: dict,
        params: dict,
        callbacks: ServiceCallbacks = None,
        stop_flag: Callable[[], bool] = None,
    ) -> dict:
        """
        基于 validate 结果执行精准增量同步（smart sync）。

        直接消费 validate_kline 的扫描结果，按问题类型分层选择同步策略，
        避免全量重写 Parquet。复用 build_download_plan 分层算法，
        内部调用 DataService.sync() 执行实际同步（miniQMT → Parquet）。

        与 smart_download 的本质区别：
          - smart_download：miniQMT 本地缓存 → miniQMT 本地缓存（下载数据到 miniQMT）
          - sync_smart：miniQMT 本地缓存 → Parquet 缓存（将 miniQMT 已有数据精准写入 Parquet）

        分层策略：
          Layer A（全量层）：has_cache == False 的标的 → 全量同步（从 open_date 或 default_start 到今天）
          Layer B（缺口层）：存在 gap_segments / head_gap_segments → 按段精准同步
          Layer C（增量层）：tail_missing > 0 → 增量同步（从最早 tail_start 到今天）

        params 字段：
            period:        str  数据周期，如 '1d'（必填）
            default_start: str  Layer A 全量同步时，若标的无 open_date 则使用此起始日期（YYYYMMDD，可选）

        返回：
            {
                'success':        bool,  # 未中断且无失败批次
                'total_batches':  int,   # 总批次数
                'done_batches':   int,   # 已执行批次数
                'failed_batches': int,   # 失败批次数
                'sync_count':     int,   # 同步标的数（去重）
                'skipped_count':  int,   # 跳过标的数
                'interrupted':    bool,
                'layer_a_count':  int,   # Layer A 同步标的数
                'layer_b_count':  int,   # Layer B 同步标的数
                'layer_c_count':  int,   # Layer C 同步标的数
            }

        注意事项：
          - 必须先调用 validate_kline 获取 validate_result，再传入此方法
          - validate_result 在内存中传递，不写入磁盘
          - 当前仅支持 stock/kline；其他子类的 smart sync 留待后续扩展
          - Layer C 的 start_date 取所有后缺失标的中最早的 tail_start，end_date = 今天
          - 某批次失败不中断整体流程，记录失败信息后继续下一批次
          - 内部调用 DataService.sync()，不绕过现有同步管道
        """

    # ── 缓存管理 ──────────────────────────────────────────────
    def get_cache_statistics(self) -> dict: ...
    def clear_all_cache(self) -> dict: ...
    def clear_symbol_cache(self, symbol: str, period: str = None) -> dict: ...

    # ── 查询接口 ──────────────────────────────────────────────
    def query_kline(
        self,
        symbol: str,
        period: str,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """从本地 Parquet 缓存查询 K 线数据（同步方法）"""

    def get_pool(self, pool_name: str, pools_cache_dir: str = None) -> list:
        """从本地 Parquet 缓存读取股票池，返回 [[code, name], ...] 格式"""
```

#### Layer 1 核心模块清单（data_manager）

| 子模块 | 文件 | 职责 |
|--------|------|------|
| `storage` | `data_manager/storage.py` | Parquet 读写引擎（Storage） |
| `sync_manager` | `data_manager/sync_manager.py` | 同步状态元数据管理 |
| `sync_pipeline` | `data_manager/sync_pipeline.py` | 数据同步框架（Source/Sink/Pipeline） |
| `cache_manager` | `data_manager/cache_manager.py` | 缓存统计、校验、清理 |
| `query_api` | `data_manager/query_api.py` | 统一 K 线查询接口 |
| `aux_data` | `data_manager/aux_data.py` | 交易日历 + 合约信息持久化 |
| `data_integrity` | `data_manager/data_integrity.py` | **数据完整性检测（缺口计算 + 全面健康检查）** |
| `asset_types` | `data_manager/asset_types.py` | 品类体系定义（含 SubTypeConfig 补充能力声明） |
| `download_handlers` | `data_manager/download_handlers.py` | **通用补充处理器注册机制 + 批量分层算法（downloadPlan）** |
| `migration` | `data_manager/migration.py` | 数据迁移 |

#### SubTypeConfig 补充能力字段（asset_types.py）

`SubTypeConfig` 新增以下字段，用于 smart download 框架自动适配，无需为每个品类单独实现补充逻辑：

| 字段 | 类型 | 说明 |
|------|------|------|
| `download_strategy` | `List[str]` | 支持的补充策略列表，可选值：`'full'` / `'incremental'` / `'gap'`；空列表表示暂不支持 smart 补充 |
| `download_handler` | `Optional[str]` | 补充处理器标识，框架根据此标识路由到具体实现，如 `'kline'` / `'calendar'` / `'instrument'` / `'sector'` / `'members'` |

各子类配置一览：

| 子类 | download_strategy | download_handler |
|------|-----------------------|-------------------|
| `stock/kline` | `['full', 'incremental', 'gap']` | `'kline'` |
| `stock/calendar` | `['full']` | `'calendar'` |
| `stock/instrument` | `['full']` | `'instrument'` |
| `industry/sector_list` | `['full']` | `'sector'` |
| `industry/members` | `['full']` | `'members'` |

#### download_handlers.py 核心组件

| 组件 | 说明 |
|------|------|
| `downloadHandler` | 抽象基类，定义 `execute_batch(symbol_list, period, start, end, mode, callbacks)` 接口 |
| `KlinedownloadHandler` | K线行情处理器，内部调用 `xqshare.get_client().download_history_data2`（服务端同步封装版） |
| `InstrumentdownloadHandler` | 合约基础信息处理器，通过 `xtdata.get_instrument_detail()` 逐只获取并写入 Parquet；每 200 只上报一次进度；单只失败不中断整批 |
| `CalendardownloadHandler` | 交易日历处理器，通过 `xtdata.get_trading_dates()` 获取并全量覆盖写入 Parquet；忽略 `symbol_list`/`period`/`start`/`end` 参数 |
| `HANDLER_REGISTRY` | 处理器注册表 `dict[str, downloadHandler]`，已注册 `'kline'`、`'instrument'`、`'calendar'` |
| `downloadPlan` | 分层补充计划数据类，含 `layer_a` / `layer_b` / `layer_c` 三层任务列表 |
| `build_download_plan()` | 批量分层算法，将 validate 结果分为三层并生成 `downloadPlan` |

**新增品类处理器时**，只需实现 `downloadHandler` 子类并调用 `register_handler(id, handler)` 注册，无需修改框架其他代码。

---

## 三、`FrameworkCallbacks` 协议（强制）

### 3.1 核心原则

框架核心必须是纯 Python，可在任何环境（CLI、服务器、单元测试）中直接 `import` 和运行。

### 3.2 禁止事项（强制）

| 禁止行为 | 正确做法 |
|---------|---------|
| 框架内直接读取外部配置 | 将 `init_data_enabled` 等配置作为显式参数传入框架 |
| 框架通过多层嵌套访问外部模块 | 统一通过 `FrameworkCallbacks` 单层接口 |

### 3.3 协议定义

框架核心与外部的所有通信，必须通过 `FrameworkCallbacks` 协议进行。协议定义在 `framework/callbacks.py`：

```python
# framework/callbacks.py
from typing import Protocol

class FrameworkCallbacks(Protocol):
    def on_log(self, message: str, level: str) -> None: ...
    def on_progress(self, pct: int) -> None: ...
    def on_period_mismatch(self, message: str) -> bool: ...  # True=继续, False=停止
    def on_t0_warning(self, message: str) -> None: ...
    def on_finished(self) -> None: ...
```

**必须提供 `DefaultCallbacks` 默认实现**，所有方法有合理默认行为（日志打印到 stdout，`on_period_mismatch` 默认返回 `True`）。框架未收到 `callbacks` 参数时自动使用 `DefaultCallbacks`。

### 3.4 适配器实现规范

| 适配器类 | 所在文件 | 职责 |
|---------|---------|------|
| `DefaultCallbacks` | `framework/callbacks.py` | 默认实现，打印到 stdout |
| `CliFrameworkCallbacks` | `bt_cli.py` | 将协议方法输出到终端 |

### 3.5 `init_data_enabled` 参数化规范

`QuantFramework` 的 `run()` 或 `__init__()` 必须将 `init_data_enabled` 作为显式参数接收，**禁止**在框架内部读取配置：

```python
# ✅ 正确：显式参数传入
framework.run(init_data_enabled=True)
```

- CLI 层：从 `--init-data` 命令行参数读取后传入框架
- 默认值：`False`