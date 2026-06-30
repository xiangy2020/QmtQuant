# 实施计划：QmtQuant Data API 服务

- [ ] 1. 添加依赖并创建 `data_api/` 模块骨架
   - 在 `requirements.txt` 中添加 `fastapi` 和 `uvicorn[standard]`
   - 创建 `data_api/__init__.py`，导出公共接口
   - _需求：9.1、9.4_

- [ ] 2. 实现统一响应格式与 FastAPI 应用基础设施
   - 在 `data_api/server.py` 中创建 FastAPI 应用实例
   - 实现统一响应模型 `ApiResponse`（`code/message/data` 结构）
   - 注册全局异常处理器（500 错误不暴露堆栈）
   - 添加响应头中间件，注入 `X-QmtQuant-Version`
   - _需求：7.1、7.2、7.3、7.4_

- [ ] 3. 实现健康检查接口
   - 在 `data_api/handlers.py` 中实现 `GET /health` 路由处理逻辑
   - 返回服务状态、版本号、缓存目录路径及各数据目录文件数量统计
   - _需求：6.1、6.2_

- [ ] 4. 实现 K 线数据查询接口
   - 在 `data_api/handlers.py` 中实现 `GET /api/v1/kline` 路由
   - 通过 `DataService.query_kline()` 读取数据，禁止直接读 Parquet
   - `format=standard`（默认）：转换为 `date/open/high/low/close/volume/amount/pct_chg` 格式，`pct_chg` 由 `close/preClose` 计算
   - `format=raw`：原样返回 Parquet 字段
   - 数据不存在时返回空数组 + message 说明
   - _需求：2.1、2.2、2.3、2.4、2.5、2.6、2.7_

- [ ] 5. 实现板块成分股查询接口
   - 在 `data_api/handlers.py` 中实现 `GET /api/v1/sector` 路由
   - 不带 `name` 参数时读取 `sector_list.parquet` 返回所有板块名称列表
   - 带 `name` 参数时返回成分股列表 `[{symbol, name}, ...]`
   - _需求：3.1、3.2、3.3、3.4_

- [ ] 6. 实现合约基础信息查询接口与交易日历查询接口
   - 在 `data_api/handlers.py` 中实现 `GET /api/v1/instruments` 路由
     - 支持 `symbols` 批量查询和分页（`page/page_size`）
     - 依赖文件缺失时返回 HTTP 503
   - 在 `data_api/handlers.py` 中实现 `GET /api/v1/calendar` 路由
     - 支持 `start/end` 过滤，返回 `YYYY-MM-DD` 格式日期列表
     - 依赖文件缺失时返回 HTTP 503
   - _需求：4.1、4.2、4.3、4.4、5.1、5.2、5.3_

- [ ] 7. 实现 `data-api` CLI 子命令
   - 新建 `dm_cli/cmd_data_api.py`，遵循现有子命令风格（`RawDescriptionHelpFormatter` + epilog）[[memory:ezzxaxzq]]
   - 支持 `--host`（默认 `127.0.0.1`）和 `--port`（默认 `8765`）参数
   - 启动时打印缓存目录状态；端口占用时打印明确错误并退出
   - 在 `dm_cli/main.py` 中注册 `data-api` 子命令
   - _需求：1.1、1.2、1.3、1.4、1.5、1.6、9.2_

- [ ] 8. 实现客户端 SDK `data_api/client.py`
   - 实现 `QmtQuantClient` 类，支持 `host/port/timeout` 初始化参数
   - `get_kline(symbol, period, start, end)` → 返回 DataFrame（`STANDARD_COLUMNS` 格式）
   - `get_sector(name)` → 返回 `[[symbol, name], ...]`（与 `DataFetcherManager.get_sector()` 兼容）
   - `get_instruments(symbols)` → 返回以 symbol 为 key 的字典
   - `get_calendar(start, end)` → 返回 `YYYY-MM-DD` 日期字符串列表
   - 服务不可达时抛出 `QmtQuantConnectionError`
   - _需求：8.1、8.2、8.3、8.4、8.5、8.6_
