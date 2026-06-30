# 实施计划：项目根目录整理（Dashboard 专项）

- [ ] 1. 创建 `dashboard/` 目录并迁移 HTML 和导出脚本
   - 在根目录创建 `dashboard/` 目录
   - 将 `dashboard.html` 移动到 `dashboard/dashboard.html`
   - 将 `dashboard_export.py` 移动到 `dashboard/dashboard_export.py`
   - _需求：1.1_

- [ ] 2. 修复 `dashboard_export.py` 的路径引用
   - 将脚本中 `Path(__file__).parent` 指向 `backtest_results/` 的路径改为 `Path(__file__).parent.parent`（向上一级到项目根目录）
   - 将默认输出路径 `dashboard_data.json` 改为 `Path(__file__).parent / "dashboard_data.json"`（输出到 `dashboard/` 目录内）
   - 更新脚本末尾的提示信息，将 `dashboard.html` 改为 `dashboard/dashboard.html`
   - _需求：1.2、1.3、1.6_

- [ ] 3. 修复 `dashboard.html` 对 `dashboard_data.json` 的加载路径
   - 检查 HTML 中 fetch/加载 `dashboard_data.json` 的路径引用
   - 确认文件与 HTML 同目录后路径为 `./dashboard_data.json`（相对路径无需修改，或按实际情况调整）
   - _需求：1.4_

- [ ] 4. 删除根目录旧文件
   - 删除根目录的 `dashboard.html`（已迁移）
   - 删除根目录的 `dashboard_export.py`（已迁移）
   - 删除根目录的 `dashboard_data.json`（若存在，已由新路径接管）
   - _需求：1.5_

- [ ] 5. 将 `test_index_kline.py` 移入 `tests/` 目录
   - 将根目录的 `test_index_kline.py` 移动到 `tests/test_index_kline.py`
   - 检查文件内部是否有相对路径引用，若有则更新为从 `tests/` 目录出发的正确路径
   - 确认 `pytest.ini` 的 `testpaths` 已包含 `tests/`，确保 pytest 能发现该文件
   - _需求：2.1、2.2、2.3_

- [ ] 6. 删除空目录 `config/`
   - 确认 `config/` 目录为空后直接删除
   - _需求：3.1_

- [ ] 7. 更新 `README.md` 中 Dashboard 相关说明
   - 搜索 README 中所有 `dashboard_export.py`、`dashboard.html`、`dashboard_data.json` 的路径引用
   - 将命令示例从 `python dashboard_export.py` 更新为 `python dashboard/dashboard_export.py`
   - 将文件路径引用更新为 `dashboard/` 目录下的新路径
   - _需求：4.1、4.2_
