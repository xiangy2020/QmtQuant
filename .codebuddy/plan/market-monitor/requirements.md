# 需求文档：市场行情监控分析模块（market_monitor）

## 引言

基于现有的 K 线数据（`stock/kline`、`index/kline`）、合约信息（`stock/instrument`）、行业成分股（`industry/members`）等本地 Parquet 缓存，构建一套**每日收盘后**的市场行情监控分析模块。

模块包含三大功能：
1. **市场全景扫描**：以大盘指数为核心，结合全市场涨跌统计，输出当日市场整体温度
2. **个股异动/涨停板监控**：识别当日涨停、跌停、连板、炸板及量价异动个股
3. **行业板块轮动分析**：基于申万一级行业，计算行业涨跌排名与轮动强度

输出形式为 **HTML 报告**，风格与现有 `dashboard/dashboard.html` 保持一致。

模块遵循项目分层架构：后端逻辑在 `market_monitor/` 目录实现，CLI 入口通过 `dm_cli/cmd_monitor.py` 新增 `monitor` 子命令接入。

---

## 需求

### 需求 1：市场全景扫描

**用户故事：** 作为量化研究员，我希望每日收盘后能看到一份市场全景扫描报告，以便快速了解当日市场整体温度和资金活跃度。

#### 验收标准

1. WHEN 执行市场全景扫描 THEN 系统 SHALL 读取本地 `index/kline/1d` 数据，展示已有指数（如上证指数 000001.SH、沪深300 000300.SH）的当日涨跌幅、开高低收、成交量、成交额；若某指数数据缺失，SHALL 在对应位置显示"数据缺失"提示，不得用其他数据替代
2. WHEN 执行市场全景扫描 THEN 系统 SHALL 统计全市场（沪深A股成分股）当日涨跌分布：上涨家数、下跌家数、平盘家数、涨停家数、跌停家数
3. WHEN 执行市场全景扫描 THEN 系统 SHALL 计算全市场当日总成交额（所有 A 股 `amount` 字段求和），并与近 5 日、近 20 日均值对比，输出量能比（当日/20日均值）
4. WHEN 执行市场全景扫描 THEN 系统 SHALL 统计当日创 20 日新高、60 日新高、250 日新高的股票数量，以及创 20 日新低、60 日新低、250 日新低的股票数量
5. IF 指定日期的数据不存在 THEN 系统 SHALL 提示"该日期无数据"并退出，不得用最近有效日期静默替代
6. WHEN 执行市场全景扫描 THEN 系统 SHALL 过滤掉停牌股（`suspendFlag != 0`）和幽灵标的（`open_date` 为空且 `expire_date` 为空/0/99999999）后再做统计

---

### 需求 2：个股异动/涨停板监控

**用户故事：** 作为量化研究员，我希望每日收盘后能看到涨停板、跌停板及量价异动个股的详细列表，以便捕捉市场热点和风险信号。

#### 验收标准

1. WHEN 执行涨停板监控 THEN 系统 SHALL 输出当日涨停股列表，每条记录包含：股票代码、股票名称、所属申万一级行业、涨跌幅、成交额、是否为连板（连续涨停天数）
2. WHEN 执行涨停板监控 THEN 系统 SHALL 输出当日跌停股列表，字段同上
3. WHEN 执行涨停板监控 THEN 系统 SHALL 识别炸板股：当日最高价 >= 涨停价 且 收盘价 < 涨停价，输出炸板股列表（代码、名称、行业、最高价、收盘价、涨跌幅）
4. WHEN 执行涨停板监控 THEN 系统 SHALL 基于 `up_stop_price` / `down_stop_price` 字段判断涨跌停，不得用固定涨跌幅比例（如 ±10%）替代
5. WHEN 执行涨停板监控 THEN 系统 SHALL 识别量价异动股：当日成交量 > 近 20 日均量 × 2 倍，且收盘价突破近 20 日最高价，输出异动股列表（代码、名称、行业、量比、涨跌幅）
6. WHEN 执行涨停板监控 THEN 系统 SHALL 过滤掉停牌股和幽灵标的后再做识别
7. IF 某股票无合约信息（`up_stop_price` 为空）THEN 系统 SHALL 跳过该股票的涨跌停判断，不得用估算值替代

---

### 需求 3：行业板块轮动分析

**用户故事：** 作为量化研究员，我希望每日收盘后能看到申万一级行业的涨跌排名和近期轮动情况，以便判断资金流向和板块强弱。

#### 验收标准

1. WHEN 执行行业轮动分析 THEN 系统 SHALL 基于申万一级行业（`SW1` 前缀，不含加权版）的成分股，计算每个行业当日等权平均涨跌幅，并按涨跌幅降序排列
2. WHEN 执行行业轮动分析 THEN 系统 SHALL 同时计算每个行业近 5 日、近 10 日、近 20 日的累计等权平均涨跌幅
3. WHEN 执行行业轮动分析 THEN 系统 SHALL 统计每个行业当日涨停股数量、跌停股数量、上涨家数、下跌家数
4. WHEN 执行行业轮动分析 THEN 系统 SHALL 识别"热点行业"：当日涨停股数量最多的前 3 个行业，在报告中高亮显示
5. WHEN 执行行业轮动分析 THEN 系统 SHALL 计算行业量能变化：行业成分股当日总成交额 vs 近 20 日均值，输出量能比
6. IF 某行业成分股中有停牌股或幽灵标的 THEN 系统 SHALL 将其从该行业的计算中剔除，不影响其他成分股的统计

---

### 需求 4：HTML 报告输出

**用户故事：** 作为量化研究员，我希望监控分析结果以 HTML 文件形式输出，以便在浏览器中直观查看。

#### 验收标准

1. WHEN 任意监控分析完成 THEN 系统 SHALL 生成一个独立的 HTML 文件，文件名格式为 `market_report_{YYYYMMDD}.html`，默认输出到 `dashboard/` 目录
2. WHEN 生成 HTML 报告 THEN 系统 SHALL 将三大功能（全景扫描、涨停板监控、行业轮动）整合在同一个 HTML 文件中，通过 Tab 或分区切换展示
3. WHEN 生成 HTML 报告 THEN 系统 SHALL 使用纯 HTML + CSS + JavaScript 实现，不依赖外部 CDN，所有样式和脚本内嵌，确保离线可用
4. WHEN 生成 HTML 报告 THEN 系统 SHALL 支持表格排序（点击列头排序）、数字高亮（涨红跌绿）
5. WHEN 生成 HTML 报告 THEN 系统 SHALL 在报告顶部显示报告生成时间和数据日期

---

### 需求 5：CLI 子命令接入

**用户故事：** 作为量化研究员，我希望通过 `dm_cli.py monitor` 命令触发监控分析，以便集成到日常工作流和定时任务中。

#### 验收标准

1. WHEN 执行 `python dm_cli.py monitor` THEN 系统 SHALL 支持 `--type` 参数指定分析类型：`overview`（全景扫描）、`limit-up`（涨停板监控）、`sector`（行业轮动）、`all`（全部，默认值）
2. WHEN 执行 monitor 命令 THEN 系统 SHALL 支持 `--date` 参数指定分析日期（格式 `YYYYMMDD`），不指定则使用本地缓存中最新的有效交易日
3. WHEN 执行 monitor 命令 THEN 系统 SHALL 支持 `--output` 参数指定 HTML 输出路径，不指定则默认输出到 `dashboard/market_report_{YYYYMMDD}.html`
4. WHEN 执行 monitor 命令 THEN 系统 SHALL 支持 `--sector` 参数指定股票池板块（默认 `沪深A股`），用于全景扫描和涨停板监控的股票范围
5. WHEN 执行 `python dm_cli.py monitor --help` THEN 系统 SHALL 按项目 CLI 规范展示帮助信息（`RawDescriptionHelpFormatter` + `epilog` 典型用法示例）
6. WHEN monitor 命令执行完成 THEN 系统 SHALL 在终端输出 HTML 文件路径，提示用户用浏览器打开

---

### 需求 6：后端服务层设计

**用户故事：** 作为开发者，我希望监控分析的后端逻辑独立于 CLI，以便后续扩展（如定时任务、API 接口）。

#### 验收标准

1. WHEN 实现监控分析功能 THEN 系统 SHALL 在 `market_monitor/` 目录下实现后端逻辑，目录结构为：`__init__.py`、`market_service.py`（统一入口）、`market_overview.py`（全景扫描）、`limit_up_monitor.py`（涨停板监控）、`sector_rotation.py`（行业轮动）、`report_builder.py`（HTML 报告生成）
2. WHEN 实现后端服务 THEN 系统 SHALL 遵循项目分层架构规范，后端逻辑不依赖 CLI 层，通过 `ServiceCallbacks` 回调接口上报进度和日志
3. WHEN 实现后端服务 THEN 系统 SHALL 直接读取本地 Parquet 缓存（通过 `data_manager.storage.Storage.load()` 或 `load_parquet()`），不发起任何网络请求
4. IF 某只股票的 Parquet 文件不存在 THEN 系统 SHALL 跳过该股票并记录日志，不中断整体分析流程
5. WHEN 实现后端服务 THEN 系统 SHALL 复用 `utils/MyTT.py` 中的技术指标函数（如 `HHV`、`MA`、`BARSLASTCOUNT`）计算涨停连板、均量等指标
