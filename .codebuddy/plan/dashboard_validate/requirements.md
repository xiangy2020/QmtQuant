# 需求文档：数据完整性检查结果接入 Dashboard

## 引言

当前 `dashboard_export.py` 导出的数据仅包含缓存统计（`get_statistics()`）和回测结果（`backtest_results`），数据完整性检查（`validate_kline` / `batch_validate`）的结果完全没有被采集和展示。

本需求旨在将完整性检查结果接入 Dashboard，让用户在打开看板时能直观看到各品类数据的健康状况，无需手动执行 CLI 命令再逐行阅读输出。

完整性检查支持**多周期**（如 `1d`、`1m`、`5m` 等），每个周期独立检查、独立展示。

**涉及改动范围：**
- `dashboard_export.py`：新增完整性检查数据采集逻辑（多周期）
- `dashboard/dashboard.html`：新增"数据健康"Tab 页，支持按周期切换查看汇总与明细

---

## 需求

### 需求 1：dashboard_export.py 采集完整性检查数据（多周期）

**用户故事：** 作为开发者，我希望运行 `python dashboard_export.py` 时自动对所有已有缓存的周期执行完整性检查，并将各周期结果写入 `dashboard_data.json`，以便 dashboard 前端能按周期展示健康状况。

#### 验收标准

1. WHEN 运行 `dashboard_export.py` THEN 系统 SHALL 自动扫描本地 `stock/kline` 缓存目录，发现所有已存在缓存数据的周期（如 `1d`、`1m`、`5m` 等），并对每个周期分别执行完整性检查。
2. WHEN 完整性检查执行完毕 THEN 系统 SHALL 将所有周期的结果写入 JSON 的 `validate_by_period` 字段，结构为 `{ "1d": { "summary": {...}, "results": [...] }, "1m": { ... } }`。
3. IF 交易日历文件（`trading_calendar.parquet`）或合约信息文件（`instrument_detail.parquet`）不存在 THEN 系统 SHALL 跳过所有周期的完整性检查，在 `validate_by_period` 中写入 `{"_skipped": true, "reason": "..."}` 并打印警告，不中断整体导出流程。
4. WHEN 某个周期的完整性检查执行完毕 THEN 该周期的 `summary` SHALL 包含以下字段：`total`、`healthy`、`no_cache`、`field_error`、`type_error`、`head_missing`、`tail_missing`、`no_open_date`、`has_gap`（中间缺口数）、`period`（周期名称）、`checked_at`（检查时间戳）。
5. WHEN 某个周期的完整性检查执行完毕 THEN 该周期的 `results` 列表中每条记录 SHALL 包含：`symbol`、`has_cache`、`field_ok`、`type_ok`、`head_missing`、`tail_missing`、`gap_count`（`gap_segments` 的段数）、`no_open_date`、`cache_start`、`cache_end`。
6. IF 完整性检查耗时超过 60 秒 THEN 系统 SHALL 在终端打印进度（每 100 只打印一次），不静默等待。
7. WHEN 导出完成 THEN 系统 SHALL 在终端按周期分别打印完整性检查的汇总统计（健康数/总数、各问题类型数量）。
8. IF 某个周期检查过程中发生异常 THEN 系统 SHALL 跳过该周期并记录错误信息，继续检查其余周期，不中断整体导出流程。

---

### 需求 2：Dashboard 新增"数据健康"Tab 页（多周期）

**用户故事：** 作为开发者，我希望在 Dashboard 中看到一个独立的"数据健康"Tab，支持按周期切换查看完整性检查的汇总指标和问题明细，以便快速判断各周期数据质量。

#### 验收标准

1. WHEN 打开 Dashboard THEN 系统 SHALL 在 Tab 导航栏中新增"🩺 数据健康"按钮，位于"数据分析"和"策略绩效"之间。
2. WHEN 切换到"数据健康"Tab 且存在多个周期数据 THEN 系统 SHALL 在内容区顶部展示周期切换按钮组（如 `1d` / `1m` / `5m`），默认选中第一个周期。
3. WHEN 选中某个周期 THEN 系统 SHALL 展示该周期的汇总指标卡片行，包含：总检查数、健康数（绿色）、无缓存数（灰色）、前缺失数（橙色）、后缺失数（橙色）、中间缺口数（红色）。
4. WHEN `validate_by_period._skipped == true` THEN 系统 SHALL 显示空状态提示："辅助数据未就绪，请先执行 `dm sync --asset stock --sub calendar` 和 `dm sync --asset stock --sub instrument`"。
5. WHEN 选中某个周期且该周期 `results` 存在且非空 THEN 系统 SHALL 展示问题股票明细表格，列包含：股票代码、缓存起止日期、前缺失天数、后缺失天数、中间缺口段数、健康状态（图标）。
6. WHEN 明细表格展示时 THEN 系统 SHALL 默认只显示有问题的股票（`healthy == false`），并提供"显示全部"切换按钮。
7. WHEN 明细表格展示时 THEN 系统 SHALL 支持按"前缺失"、"后缺失"、"缺口段数"列排序（点击列头切换升/降序）。
8. IF `validate_by_period` 为空或不存在 THEN 系统 SHALL 显示空状态提示："暂无检查数据，请重新运行 `python dashboard_export.py`"。
9. WHEN 某周期健康率达到 100% THEN 系统 SHALL 在该周期汇总区域显示绿色"✅ 数据完全健康"标识。

---

### 需求 3：性能与兼容性

**用户故事：** 作为开发者，我希望多周期完整性检查不会让 `dashboard_export.py` 的运行时间过长，且不影响现有 Dashboard 功能。

#### 验收标准

1. WHEN 股票池超过 5000 只时 THEN 系统 SHALL 通过 `batch_validate` 批量执行，不逐只串行调用，确保单个周期的检查时间在可接受范围内。
2. WHEN `dashboard_data.json` 中不含 `validate_by_period` 字段（旧版本数据）THEN Dashboard SHALL 在"数据健康"Tab 显示空状态提示，不报错、不崩溃。
3. WHEN 完整性检查中某只股票抛出异常 THEN 系统 SHALL 记录该股票的错误信息并继续检查其余股票，不中断整体流程。
4. IF 本地缓存中只有一个周期的数据 THEN 系统 SHALL 不显示周期切换按钮组，直接展示该周期的汇总与明细。
