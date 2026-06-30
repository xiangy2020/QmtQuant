# QmtQuant Data API 服务需求文档

## 引言

QmtQuant 项目通过 miniQMT 积累了高质量的本地 Parquet 缓存数据（K线、合约信息、交易日历、行业板块等）。为了让其他项目（如 `daily_stock_analysis`、未来更多项目）能够复用这些数据，需要在 QmtQuant 内部构建一个轻量级 HTTP API 服务。

该服务基于 **FastAPI + uvicorn**，以 `data-api` 子命令集成到现有 `dm_cli` 体系中，对外暴露统一的 REST 接口，并提供配套的客户端 SDK（`client.py`），供其他项目一键接入。

---

## 需求

### 需求 1：HTTP API 服务启动与管理

**用户故事：** 作为开发者，我希望通过 `dm_cli` 的 `data-api` 子命令启动/停止 HTTP API 服务，以便统一管理所有数据相关命令。

#### 验收标准

1. WHEN 执行 `python dm_cli.py data-api --port 8765` THEN 系统 SHALL 在指定端口启动 FastAPI + uvicorn 服务，并在终端打印服务地址和已注册的接口列表。
2. WHEN 执行 `python dm_cli.py data-api --host 0.0.0.0 --port 8765` THEN 系统 SHALL 监听所有网络接口，允许局域网内其他机器访问。
3. WHEN 服务启动时 THEN 系统 SHALL 打印当前缓存根目录路径（`~/.qmtquant/cache`）和各数据目录的文件数量，方便确认数据就绪状态。
4. WHEN 用户按 Ctrl+C THEN 系统 SHALL 优雅关闭服务，不留残留进程。
5. WHEN `--port` 参数未指定 THEN 系统 SHALL 使用默认端口 `8765`。
6. WHEN 指定端口已被占用 THEN 系统 SHALL 打印明确的错误信息并退出，不崩溃。

---

### 需求 2：K线数据查询接口

**用户故事：** 作为调用方项目，我希望通过 HTTP 接口查询指定股票的 K 线数据，并获得与 `daily_stock_analysis` `STANDARD_COLUMNS` 格式兼容的响应，以便直接接入现有分析流程。

#### 验收标准

1. WHEN 请求 `GET /api/v1/kline?symbol=600519.SH&period=1d&start=20240101&end=20241231` THEN 系统 SHALL 返回该股票在指定日期范围内的日线数据，HTTP 状态码 200。
2. WHEN `format=standard`（默认）THEN 系统 SHALL 返回包含字段 `date, open, high, low, close, volume, amount, pct_chg` 的 JSON 数组，其中 `date` 为 `YYYY-MM-DD` 字符串，`pct_chg` 由 `close` 和 `preClose` 计算得出（百分比，保留两位小数）。
3. WHEN `format=raw` THEN 系统 SHALL 返回 Parquet 文件中的原始字段（不做任何转换），供高级用户使用。
4. WHEN `start` 或 `end` 参数未指定 THEN 系统 SHALL 返回该股票的全量缓存数据。
5. WHEN 指定股票的 Parquet 文件不存在 THEN 系统 SHALL 返回 HTTP 200，`data` 字段为空数组 `[]`，并在 `message` 字段说明原因。
6. WHEN `symbol` 参数缺失 THEN 系统 SHALL 返回 HTTP 422，包含参数校验错误信息。
7. WHEN `period` 参数未指定 THEN 系统 SHALL 默认使用 `1d`。

---

### 需求 3：板块成分股查询接口

**用户故事：** 作为调用方项目，我希望通过 HTTP 接口查询指定板块的成分股列表，以便获取选股池。

#### 验收标准

1. WHEN 请求 `GET /api/v1/sector?name=沪深300` THEN 系统 SHALL 返回该板块的成分股列表，格式为 `[{"symbol": "600519.SH", "name": "贵州茅台"}, ...]`，HTTP 状态码 200。
2. WHEN 指定板块的 Parquet 文件不存在 THEN 系统 SHALL 返回 HTTP 200，`data` 字段为空数组 `[]`，并在 `message` 字段说明原因。
3. WHEN `name` 参数缺失 THEN 系统 SHALL 返回 HTTP 422，包含参数校验错误信息。
4. WHEN 请求 `GET /api/v1/sector` 不带 `name` 参数 THEN 系统 SHALL 返回所有可用板块名称列表（读取 `industry/sector_list/sector_list.parquet`）。

---

### 需求 4：合约基础信息查询接口

**用户故事：** 作为调用方项目，我希望通过 HTTP 接口查询股票的合约基础信息（上市日期、总股本、流通股本等），以便在分析中使用基本面数据。

#### 验收标准

1. WHEN 请求 `GET /api/v1/instruments?symbols=600519.SH,000001.SZ` THEN 系统 SHALL 返回这两只股票的合约信息，格式为 `[{"symbol": "600519.SH", "name": "贵州茅台", "open_date": "20010827", ...}, ...]`，HTTP 状态码 200。
2. WHEN `symbols` 参数未指定 THEN 系统 SHALL 返回全量合约信息（分页，默认 `page=1&page_size=500`）。
3. WHEN 某个 symbol 在合约信息中不存在 THEN 系统 SHALL 跳过该 symbol，不影响其他 symbol 的返回。
4. WHEN `instrument_detail.parquet` 文件不存在 THEN 系统 SHALL 返回 HTTP 503，提示用户先执行 `sync --asset stock --sub instrument`。

---

### 需求 5：交易日历查询接口

**用户故事：** 作为调用方项目，我希望通过 HTTP 接口查询 A 股交易日历，以便在分析中判断某天是否为交易日。

#### 验收标准

1. WHEN 请求 `GET /api/v1/calendar?start=20240101&end=20241231` THEN 系统 SHALL 返回指定范围内的所有交易日列表，格式为 `["2024-01-02", "2024-01-03", ...]`，HTTP 状态码 200。
2. WHEN `start` 或 `end` 参数未指定 THEN 系统 SHALL 返回全量交易日历。
3. WHEN `trading_calendar.parquet` 文件不存在 THEN 系统 SHALL 返回 HTTP 503，提示用户先执行 `sync --asset stock --sub calendar`。

---

### 需求 6：健康检查接口

**用户故事：** 作为调用方项目，我希望通过健康检查接口确认服务是否正常运行，以便在接入前做可用性验证。

#### 验收标准

1. WHEN 请求 `GET /health` THEN 系统 SHALL 返回 HTTP 200，包含服务状态、版本号、缓存目录路径、各数据目录的文件数量统计。
2. WHEN 服务正常运行 THEN `status` 字段 SHALL 为 `"ok"`。

---

### 需求 7：统一响应格式与错误处理

**用户故事：** 作为调用方项目，我希望所有接口返回统一的 JSON 格式，以便客户端 SDK 统一解析。

#### 验收标准

1. WHEN 任意接口请求成功 THEN 系统 SHALL 返回格式 `{"code": 0, "message": "ok", "data": ...}`。
2. WHEN 任意接口发生业务错误（如数据不存在）THEN 系统 SHALL 返回格式 `{"code": <非0>, "message": "<错误描述>", "data": null}`，HTTP 状态码视情况为 200/422/503。
3. WHEN 服务内部发生未捕获异常 THEN 系统 SHALL 返回 HTTP 500，`message` 字段包含错误摘要，不暴露完整堆栈信息给调用方。
4. WHEN 所有接口响应 THEN 系统 SHALL 在响应头中包含 `X-QmtQuant-Version` 字段，值为当前版本号。

---

### 需求 8：客户端 SDK

**用户故事：** 作为其他项目的开发者，我希望有一个开箱即用的 Python 客户端 SDK，以便无需手动拼接 HTTP 请求即可调用 QmtQuant 数据。

#### 验收标准

1. WHEN 其他项目复制 `data_api/client.py` 后 THEN 开发者 SHALL 能通过 `QmtQuantClient(host, port).get_kline(symbol, period, start, end)` 获取 DataFrame，字段与 `STANDARD_COLUMNS` 一致。
2. WHEN 调用 `get_sector(name)` THEN 客户端 SHALL 返回 `[[symbol, name], ...]` 格式的列表，与 `daily_stock_analysis` 的 `DataFetcherManager.get_sector()` 返回格式兼容。
3. WHEN 调用 `get_instruments(symbols)` THEN 客户端 SHALL 返回以 symbol 为 key 的字典。
4. WHEN 调用 `get_calendar(start, end)` THEN 客户端 SHALL 返回日期字符串列表（`YYYY-MM-DD` 格式）。
5. WHEN 服务不可达（连接超时/拒绝）THEN 客户端 SHALL 抛出明确的 `QmtQuantConnectionError` 异常，不返回空数据。
6. WHEN SDK 初始化时 THEN 客户端 SHALL 支持 `timeout` 参数（默认 10 秒）。

---

### 需求 9：模块结构与集成

**用户故事：** 作为项目维护者，我希望 API 服务代码遵循现有项目的分层架构规范，以便与现有模块保持一致。

#### 验收标准

1. WHEN 新增 API 服务模块 THEN 系统 SHALL 在 `data_api/` 目录下组织代码，包含 `__init__.py`、`server.py`（FastAPI 应用）、`handlers.py`（业务处理逻辑）、`client.py`（客户端 SDK）。
2. WHEN `data-api` 子命令注册 THEN 系统 SHALL 在 `dm_cli/cmd_data_api.py` 中实现，并在 `dm_cli/main.py` 中注册，遵循现有子命令风格（`RawDescriptionHelpFormatter` + epilog）。
3. WHEN API 服务读取数据 THEN 系统 SHALL 通过 `DataService` 的现有方法（`query_kline`、`get_sector` 等）访问数据，禁止直接读取 Parquet 文件绕过服务层。
4. WHEN `fastapi` 和 `uvicorn` 依赖 THEN 系统 SHALL 将其添加到 `requirements.txt`。
