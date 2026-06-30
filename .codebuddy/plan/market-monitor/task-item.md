# 实施计划：市场行情监控分析模块（market_monitor）

- [ ] 1. 搭建 `market_monitor/` 模块骨架
   - 创建目录及 `__init__.py`，定义公共接口导出
   - 在 `market_monitor/market_service.py` 中定义 `MarketMonitorService` 类骨架，接入 `ServiceCallbacks` 回调接口
   - 在 `data_manager/aux_data.py` 或工具模块中实现/复用 `is_ghost_symbol()` 幽灵标的判定函数
   - _需求：6.1、6.2_

- [ ] 2. 实现数据加载公共层（`market_monitor/data_loader.py`）
   - 封装从本地 Parquet 缓存加载股票 K 线、指数 K 线、合约信息、行业成分股的公共函数
   - 实现"获取最新有效交易日"逻辑（扫描缓存索引，不依赖 sync_meta）
   - 实现停牌股 + 幽灵标的过滤逻辑，统一调用 `is_ghost_symbol()`
   - _需求：1.5、1.6、2.6、6.3、6.4_

- [ ] 3. 实现市场全景扫描（`market_monitor/market_overview.py`）
   - 读取 `index/kline/1d`，输出各指数当日开高低收/涨跌幅/成交量/成交额，数据缺失显示"数据缺失"
   - 统计全市场涨跌分布（上涨/下跌/平盘/涨停/跌停家数），基于 `up_stop_price`/`down_stop_price` 判断涨跌停
   - 计算全市场总成交额及与近 5 日、近 20 日均值对比，输出量能比
   - 统计创 20/60/250 日新高、新低的股票数量（复用 `utils/MyTT.py` 的 `HHV`/`LLV`）
   - _需求：1.1、1.2、1.3、1.4、1.6_

- [ ] 4. 实现涨停板/个股异动监控（`market_monitor/limit_up_monitor.py`）
   - 输出涨停股列表（代码、名称、行业、涨跌幅、成交额、连板天数），连板计算复用 `BARSLASTCOUNT`
   - 输出跌停股列表（字段同上）
   - 识别炸板股（最高价 >= 涨停价 且 收盘价 < 涨停价）
   - 识别量价异动股（成交量 > 近 20 日均量 × 2 且收盘价突破近 20 日最高价）
   - 无合约信息（`up_stop_price` 为空）时跳过该股，不估算
   - _需求：2.1、2.2、2.3、2.4、2.5、2.7_

- [ ] 5. 实现行业板块轮动分析（`market_monitor/sector_rotation.py`）
   - 加载申万一级行业（`SW1` 前缀，不含加权版）成分股，过滤停牌股和幽灵标的
   - 计算每个行业当日等权平均涨跌幅，并按降序排列
   - 计算每个行业近 5/10/20 日累计等权平均涨跌幅
   - 统计每个行业涨停/跌停/上涨/下跌家数，识别热点行业（涨停数最多前 3 个）
   - 计算行业量能比（当日总成交额 vs 近 20 日均值）
   - _需求：3.1、3.2、3.3、3.4、3.5、3.6_

- [ ] 6. 实现 HTML 报告生成（`market_monitor/report_builder.py`）
   - 设计三 Tab 页面结构（全景扫描 / 涨停板监控 / 行业轮动），顶部显示报告生成时间和数据日期
   - 实现涨红跌绿数字高亮、表格点击列头排序（纯内嵌 JS，不依赖外部 CDN）
   - 热点行业高亮显示（涨停数最多前 3 个行业行背景色区分）
   - 输出文件名格式 `market_report_{YYYYMMDD}.html`，默认写入 `dashboard/` 目录
   - _需求：4.1、4.2、4.3、4.4、4.5、3.4_

- [ ] 7. 整合服务入口（`market_monitor/market_service.py`）
   - 实现 `MarketMonitorService.run(params, callbacks)` 统一入口，按 `type` 参数分发调用各子模块
   - 通过 `ServiceCallbacks` 上报进度和日志，单只股票失败不中断整体流程
   - _需求：6.2、6.4_

- [ ] 8. 实现 CLI 子命令（`dm_cli/cmd_monitor.py`）并接入 `dm_cli.py`
   - 新增 `monitor` 子命令，支持 `--type`、`--date`、`--output`、`--sector` 参数
   - 按项目 CLI 规范实现 `RawDescriptionHelpFormatter` + `epilog` 典型用法示例
   - 命令完成后在终端输出 HTML 文件路径，提示用户用浏览器打开
   - _需求：5.1、5.2、5.3、5.4、5.5、5.6_
