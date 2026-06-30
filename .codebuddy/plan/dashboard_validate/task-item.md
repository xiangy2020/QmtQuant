# 实施计划：数据完整性检查结果接入 Dashboard

- [ ] 1. 在 `dashboard_export.py` 中新增周期自动发现函数
   - 扫描本地 `stock/kline` 缓存目录，返回所有已有数据的周期列表（如 `['1d', '5m']`）
   - 利用 `get_statistics()` 返回的 `asset_types.stock.periods` 字段，或直接扫描缓存目录结构
   - _需求：1.1_

- [ ] 2. 在 `dashboard_export.py` 中新增辅助数据可用性检查函数
   - 检查 `trading_calendar.parquet` 和 `instrument_detail.parquet` 是否存在
   - 不存在时返回 `{"_skipped": True, "reason": "..."}` 并打印警告
   - _需求：1.3_

- [ ] 3. 在 `dashboard_export.py` 中新增 `collect_validate_results()` 函数，对每个周期执行完整性检查
   - 调用 `DataService.validate_kline()` 对每个周期的股票池执行批量检查（通过 `batch_validate`）
   - 将每个周期的 `summary`（含 `total`、`healthy`、`no_cache`、`field_error`、`type_error`、`head_missing`、`tail_missing`、`no_open_date`、`has_gap`、`period`、`checked_at`）和 `results`（每只股票的 `symbol`、`has_cache`、`field_ok`、`type_ok`、`head_missing`、`tail_missing`、`gap_count`、`no_open_date`、`cache_start`、`cache_end`）写入 `validate_by_period` 字典
   - 每 100 只打印一次进度；单只股票异常不中断；单个周期异常跳过并继续
   - 导出完成后按周期打印汇总统计
   - _需求：1.1、1.2、1.4、1.5、1.6、1.7、1.8、3.1、3.3_

- [ ] 4. 在 `dashboard_export.py` 的 `main()` 中集成完整性检查采集
   - 在 `get_statistics()` 和 `collect_backtest_results()` 之后，调用辅助数据检查和 `collect_validate_results()`
   - 将返回结果赋值给 `stats["validate_by_period"]`，随其他数据一起写入 JSON
   - _需求：1.2、1.3_

- [ ] 5. 在 `dashboard.html` 中新增"数据健康"Tab 的 HTML 结构和 CSS 样式
   - 在 Tab 导航栏中插入"🩺 数据健康"按钮（位于"数据分析"和"策略绩效"之间）
   - 新增对应的 `<div class="tab-pane" id="tab-health">` 内容容器
   - 新增周期切换按钮组、汇总指标卡片行、明细表格的 CSS 样式（复用现有 `.metrics-grid`、`.metric-card`、`.table-wrap` 等样式，按需补充）
   - _需求：2.1、2.2、2.3_

- [ ] 6. 在 `dashboard.html` 中实现 `renderHealthPage()` 渲染函数
   - 处理 `validate_by_period` 不存在或 `_skipped == true` 时的空状态/提示展示（需求 2.4、2.8）
   - 单周期时直接展示，多周期时渲染周期切换按钮组，默认选中第一个周期（需求 2.2、3.4）
   - 渲染汇总指标卡片（总数、健康数绿色、无缓存灰色、前缺失橙色、后缺失橙色、缺口数红色）；健康率 100% 时显示"✅ 数据完全健康"（需求 2.3、2.9）
   - 渲染明细表格：默认只显示有问题股票，提供"显示全部"切换按钮；支持按前缺失/后缺失/缺口段数列排序（需求 2.5、2.6、2.7）
   - _需求：2.1 ~ 2.9、3.2、3.4_

- [ ] 7. 在 `dashboard.html` 的 `renderAll()` / `loadData()` 中集成健康页渲染
   - 在 `loadData()` 成功回调中调用 `renderHealthPage(data)`
   - 确保旧版 JSON（不含 `validate_by_period`）不报错、不崩溃
   - _需求：3.2_
