# 需求文档：项目根目录整理（Dashboard 专项）

## 引言

项目根目录目前存在文件散落问题，尤其是 Dashboard（数据看板）相关的三个文件（`dashboard.html`、`dashboard_data.json`、`dashboard_export.py`）直接堆放在根目录，与项目核心模块混杂在一起，影响可读性和可维护性。

此外还存在以下次要问题：
- `test_index_kline.py` 测试文件散落在根目录（应归入 `tests/`）
- `config/` 是空目录，与 `config/` 并存，命名混乱

本次整理目标：将 Dashboard 相关文件收纳到专属目录，同时清理其他根目录杂项，使根目录保持整洁、职责清晰。

---

## 需求

### 需求 1：将 Dashboard 相关文件迁移到专属目录

**用户故事：** 作为开发者，我希望 Dashboard 相关文件（HTML、数据 JSON、导出脚本）统一收纳在 `dashboard/` 目录下，以便根目录保持整洁，Dashboard 功能的文件一目了然。

#### 验收标准

1. WHEN 整理完成 THEN 系统 SHALL 在根目录下存在 `dashboard/` 目录，包含以下文件：
   - `dashboard/dashboard.html`（原 `dashboard.html`）
   - `dashboard/dashboard_export.py`（原 `dashboard_export.py`）
2. WHEN 整理完成 THEN 系统 SHALL 将 `dashboard_data.json` 的默认输出路径更新为 `dashboard/dashboard_data.json`，使数据文件也生成在 `dashboard/` 目录内
3. WHEN `dashboard_export.py` 被移动后 THEN 系统 SHALL 更新脚本内部的路径引用（`Path(__file__).parent` 相关逻辑），确保脚本从新位置运行时仍能正确找到 `backtest_results/` 目录和输出路径
4. WHEN `dashboard.html` 被移动后 THEN 系统 SHALL 更新 HTML 文件内部对 `dashboard_data.json` 的引用路径，确保浏览器打开时能正确加载数据
5. IF 根目录存在旧的 `dashboard.html`、`dashboard_data.json`、`dashboard_export.py` THEN 系统 SHALL 将这些文件从根目录删除（迁移完成后清理）
6. WHEN 用户运行 `python dashboard/dashboard_export.py` THEN 系统 SHALL 正常生成 `dashboard/dashboard_data.json` 并提示用浏览器打开 `dashboard/dashboard.html`

---

### 需求 2：将散落的测试文件归入 tests/ 目录

**用户故事：** 作为开发者，我希望所有测试文件都在 `tests/` 目录下，以便根目录不被测试文件污染，测试管理更集中。

#### 验收标准

1. WHEN 整理完成 THEN 系统 SHALL 将根目录的 `test_index_kline.py` 移动到 `tests/test_index_kline.py`
2. WHEN 文件移动后 THEN 系统 SHALL 确认 `pytest.ini` 的 `testpaths` 配置能覆盖 `tests/` 目录，使 pytest 仍能发现该测试文件
3. IF `test_index_kline.py` 内部有相对路径引用 THEN 系统 SHALL 更新这些路径，确保从 `tests/` 目录运行时路径正确

---

### 需求 3：清理空目录 config/

**用户故事：** 作为开发者，我希望根目录不存在空的、命名混乱的目录，以便项目结构清晰，不产生歧义。

#### 验收标准

1. WHEN 整理完成 THEN 系统 SHALL 删除根目录下的空目录 `config/`（与 `config/` 并存且为空，无保留价值）
2. IF `config/` 目录非空（存在文件）THEN 系统 SHALL 先确认内容后再决定是否删除或合并到 `config/`

---

### 需求 4：更新相关文档和使用说明

**用户故事：** 作为开发者，我希望 README 和相关文档中关于 Dashboard 的使用说明路径是最新的，以便用户能按文档正确操作。

#### 验收标准

1. WHEN Dashboard 文件迁移完成后 THEN 系统 SHALL 检查 `README.md` 中关于 Dashboard 的使用说明，将路径从根目录更新为 `dashboard/` 目录
2. WHEN 整理完成 THEN 系统 SHALL 确保 `README.md` 中的运行命令示例（如 `python dashboard_export.py`）更新为 `python dashboard/dashboard_export.py`
