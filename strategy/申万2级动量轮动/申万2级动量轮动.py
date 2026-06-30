# coding: utf-8
# 策略说明：
# - 策略名称：申万2级动量板块轮动
# - 功能：每周第一个交易日，计算所有申万2级行业板块的近5日成分股加权涨幅，
#         选出动量最强的板块，买入该板块涨幅最大的前2只成分股（各50%仓位）
# - 换仓频率：每周固定换仓（每周第一个交易日）
# - 止损：3%，移动止盈：盈利达3%后激活，从盈利高点回落2%止盈（每日检查）
# - 回测时间：20241231 ~ 20260531，初始资金：10万
from utils.quant_import import *

# ===== 策略参数 =====
STOP_LOSS_RATIO          = 0.03   # 止损比例：跌超3%卖出
TRAILING_PROFIT_ACTIVATE = 0.03   # 移动止盈激活阈值：盈利达3%后开始追踪
TRAILING_PROFIT_CALLBACK = 0.02   # 移动止盈回撤比例：从盈利高点回落2%止盈
TOP_N_STOCKS      = 2      # 每次买入板块内涨幅最大的前N只股票
MOMENTUM_DAYS     = 5      # 动量计算周期（近N根K线涨幅）
MOMENTUM_PERIOD   = "1d"   # 动量计算使用的K线粒度（独立于框架驱动周期）
EACH_STOCK_RATIO  = 0.50   # 每只股票使用资金比例（2只各50%）

# ===== 全局状态 =====
g = {
    "sw2_sectors": [],      # 申万2级行业板块名称列表（初始化时加载）
}

# 止损止盈管理器（在 init() 中初始化）
stop_manager: StopLossManager = None
# 驱动周期适配器（在 init() 中初始化）
freq_adapter: BarFrequencyAdapter = None

def _log(data: Dict, message: str, level: str = "INFO") -> None:
    """通过框架回调输出日志，走 CliFrameworkCallbacks.on_log() 显示到终端"""
    try:
        fw = data.get("__framework__")
        if fw is not None:
            fw._log(message, level)
            return
    except Exception:
        pass
    logging.info(message)  # 兜底

def init(stocks=None, data=None):
    """策略初始化：加载申万2级行业板块列表，初始化止损止盈管理器和周期适配器"""
    global stop_manager, freq_adapter
    # 初始化止损止盈管理器（类型A：周期透明，每次 on_bar 都执行）
    stop_manager = StopLossManager(
        stop_loss=STOP_LOSS_RATIO,
        trailing_profit_activate=TRAILING_PROFIT_ACTIVATE,
        trailing_profit_callback=TRAILING_PROFIT_CALLBACK,
        price_field="open",
    )
    # 初始化驱动周期适配器（类型B：周期锁定，屏蔽驱动周期差异）
    # daily_trigger_time：分钟驱动时，每日在 09:31 触发一次日级别逻辑
    freq_adapter = BarFrequencyAdapter(daily_trigger_time="09:31:00")

    all_sectors = xtdata.get_sector_list()
    # 筛选申万2级行业板块：以 "SW2" 开头，且不含"加权"、"等权"等指数变体后缀
    _EXCLUDE_KEYWORDS = ("加权", "等权", "指数", "全收益")
    sw2_sectors = [
        s for s in all_sectors
        if s.startswith("SW2") and not any(kw in s for kw in _EXCLUDE_KEYWORDS)
    ]
    g["sw2_sectors"] = sw2_sectors
    logging.info(f"已加载申万2级行业板块 {len(sw2_sectors)} 个")
    if not sw2_sectors:
        logging.warning("未找到申万2级行业板块，请先执行 xtdata.download_sector_data() 下载板块数据")

def _batch_fetch_closes(stock_list: list, end_date: str, count: int) -> Dict[str, np.ndarray]:
    """批量获取多只股票截止 end_date 的最近 count 根K线收盘价（前复权）

    使用 MOMENTUM_PERIOD 指定K线粒度，与框架驱动周期无关。
    一次 RPC 拉取整个板块所有成分股，避免逐只请求。
    返回：{stock_code: np.ndarray}，获取失败的股票不在结果中
    """
    if not stock_list:
        return {}
    try:
        end_dt = end_date + "000000"
        raw = xtdata.get_market_data_ex(
            field_list=["close"],
            stock_list=stock_list,
            period=MOMENTUM_PERIOD,   # 动量计算粒度，独立于驱动周期
            start_time="",
            end_time=end_dt,
            count=count,
            dividend_type="front",
        )
        if not raw:
            return {}
        result = {}
        for sc, df in raw.items():
            if df is None or df.empty:
                continue
            arr = df["close"].dropna().values
            arr = arr[arr > 0]  # 过滤价格为 0 的脏数据
            if len(arr) > 0:
                result[sc] = arr
        return result
    except Exception as e:
        logging.debug(f"批量获取收盘价出错: {e}")
        return {}

def _calc_sector_score_and_top_stocks(sector_name: str, dn: str, top_n: int):
    """计算板块动量分，同时返回涨幅最大的前N只股票及其最新收盘价（一次批量请求，两用）

    Returns:
        (score: float, top_stocks: list of (stock_code, latest_close))
        score=-999.0 表示数据不足
    """
    try:
        members = xtdata.get_stock_list_in_sector(sector_name)
        if not members:
            return -999.0, []

        # 一次批量 RPC 拉取整个板块所有成分股
        closes_map = _batch_fetch_closes(members, dn, MOMENTUM_DAYS + 2)

        returns = []
        stock_returns = []
        for sc, closes in closes_map.items():
            if len(closes) < MOMENTUM_DAYS + 1:
                continue
            base = closes[-(MOMENTUM_DAYS + 1)]
            if base <= 0:
                continue
            ret = (closes[-1] - base) / base
            returns.append(ret)
            stock_returns.append((sc, ret, float(closes[-1])))  # 顺带保存最新收盘价

        if not returns:
            return -999.0, []

        score = float(np.mean(returns))
        stock_returns.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [(sc, price) for sc, _, price in stock_returns[:top_n]]
        return score, top_stocks
    except Exception as e:
        logging.debug(f"计算板块 {sector_name} 动量出错: {e}")
        return -999.0, []

def _do_rebalance(data: Dict) -> List[Dict]:
    """执行换仓逻辑（类型B：周期锁定，由适配器控制触发时机）

    计算所有申万2级板块动量，选出最强板块，卖出非目标持仓，买入目标股票。
    内部数据拉取使用 MOMENTUM_PERIOD（独立于框架驱动周期）。
    """
    signals = []
    dn = get_data(data, "date_num")
    positions = get_data(data, "positions")
    sw2_sectors = g["sw2_sectors"]

    if not sw2_sectors:
        _log(data, f"[{dn}] ⚠ 申万2级板块列表为空，跳过换仓", "WARNING")
        return signals

    _log(data, f"[{dn}] ══════════ 换仓日 ══════════")
    _log(data, f"[{dn}] 开始计算 {len(sw2_sectors)} 个申万2级板块动量（数据粒度: {MOMENTUM_PERIOD}）...")

    # ===== 第一步：计算所有板块动量，选出最强板块（含各板块Top股票）=====
    sector_scores = []
    sector_top_stocks = {}
    for sector in sw2_sectors:
        score, top_stocks = _calc_sector_score_and_top_stocks(sector, dn, TOP_N_STOCKS)
        sector_scores.append((sector, score))
        sector_top_stocks[sector] = top_stocks

    sector_scores.sort(key=lambda x: x[1], reverse=True)
    top_sector, top_score = sector_scores[0]

    # 打印 Top5 板块排名
    _log(data, f"[{dn}] 板块动量排名 Top5：")
    for i, (sec, sc) in enumerate(sector_scores[:5], 1):
        marker = " ◀ 选中" if i == 1 else ""
        _log(data, f"[{dn}]   {i}. {sec}  {sc:.2%}{marker}")

    # ===== 第二步：直接取已计算好的目标股票（无需再次请求）=====
    target_stocks = sector_top_stocks.get(top_sector, [])  # list of (stock_code, latest_close)
    if not target_stocks:
        _log(data, f"[{dn}] ⚠ 板块 {top_sector} 未能获取成分股，跳过换仓", "WARNING")
        return signals
    target_codes = [sc for sc, _ in target_stocks]
    _log(data, f"[{dn}] 目标持仓：{[s[:6] for s in target_codes]}")

    # ===== 第三步：卖出不在目标持仓中的股票 =====
    sell_codes = [sc for sc in positions.keys() if sc not in target_codes]
    sell_closes = _batch_fetch_closes(sell_codes, dn, 2) if sell_codes else {}
    for sc in sell_codes:
        sell_price = get_price(data, sc, "open")
        if sell_price <= 0 and sc in sell_closes:
            arr = sell_closes[sc]
            sell_price = float(arr[-1]) if len(arr) > 0 else 0
        if sell_price > 0:
            _log(data, f"[{dn}] 🔄 换仓卖出 {sc[:6]}  价格: {sell_price}", "WARNING")
            signals.extend(generate_signal(data, sc, sell_price, 1.0, "sell",
                           f"{sc[:6]} 换仓卖出"))

    # ===== 第四步：买入目标股票（无持仓则买入，使用已缓存的最新收盘价）=====
    for sc, cached_price in target_stocks:
        if not has_position(data, sc):
            buy_price = get_price(data, sc, "open")
            if buy_price <= 0:
                buy_price = cached_price
            if buy_price <= 0:
                _log(data, f"[{dn}] ⚠ {sc[:6]} 无法获取买入价格，跳过", "WARNING")
                continue
            _log(data, f"[{dn}] 🟦 买入 {sc[:6]}  价格: {buy_price}  仓位: {EACH_STOCK_RATIO:.0%}  板块: {top_sector}", "WARNING")
            signals.extend(generate_signal(data, sc, buy_price, EACH_STOCK_RATIO, "buy",
                           f"{sc[:6]} 动量轮动买入 [{top_sector}]"))

    _log(data, f"[{dn}] ══════════════════════════")
    return signals

def _inject_position_prices(data: Dict) -> None:
    """将持仓股票的最新价注入 data，供止损止盈系统使用。

    当 data 中缺少持仓股票的行情数据时（如 1m 驱动但 stock_list 不含持仓股），
    通过 get_market_data_ex 拉取最近1根K线，以 pd.Series 形式注入 data。
    已有数据的股票不覆盖（优先使用框架推送的实时数据）。

    拉取周期与框架驱动周期保持一致：
      - 1d 驱动 → period="1d"，end_time 精确到日（YYYYMMDD）
      - 其他（1m/5m 等）→ period 与驱动一致，end_time 精确到秒（YYYYMMDDHHMMSS）
    """
    positions = data.get("__positions__", {})
    if not positions:
        return
    # 找出 data 中缺失行情的持仓股票
    missing = [sc for sc in positions if sc not in data or not isinstance(data.get(sc), pd.Series)]
    if not missing:
        return

    # 从框架上下文获取驱动周期（trigger.type，而非 data.kline_period）
    drive_period = "1d"
    try:
        fw = data.get("__framework__")
        if fw is not None and hasattr(fw, "config"):
            trigger_cfg = fw.config.config_dict.get("backtest", {}).get("trigger", {})
            drive_period = trigger_cfg.get("type", "1d") or "1d"
    except Exception:
        pass

    # 根据驱动周期决定 end_time 格式
    current_time = data.get("__current_time__", {})
    ts = current_time.get("timestamp", 0)
    try:
        from datetime import datetime as _dt
        dt_obj = _dt.fromtimestamp(ts / 1000) if ts else _dt.now()
        if drive_period == "1d":
            end_dt = dt_obj.strftime("%Y%m%d")
        else:
            end_dt = dt_obj.strftime("%Y%m%d%H%M%S")
    except Exception:
        end_dt = ""

    logging.debug(f"[inject] drive_period={drive_period} end_dt={end_dt} missing={[s[:6] for s in missing]}")
    try:
        raw = xtdata.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume"],
            stock_list=missing,
            period=drive_period,
            start_time="",
            end_time=end_dt,
            count=1,
            dividend_type="front",
        )
        for sc, df in (raw or {}).items():
            if df is None or df.empty:
                logging.debug(f"[inject] {sc[:6]} 返回空 DataFrame")
                continue
            row = df.iloc[-1]
            logging.debug(f"[inject] {sc[:6]} 拉到 index={df.index[-1]} open={row.get('open', 'N/A')} close={row.get('close', 'N/A')}")
            data[sc] = row  # 注入为 pd.Series，与框架推送格式一致
    except Exception as e:
        logging.debug(f"[止损] 拉取持仓最新价失败: {e}")


def on_bar(data: Dict) -> List[Dict]:
    """策略主逻辑：每日检查止损止盈，每周换仓

    两类逻辑的驱动方式：
    - 类型A（周期透明）：stop_manager.check() 每次 on_bar 都执行，
      驱动是 1m 就每分钟检查，是 1d 就每天检查，天然适配。
    - 类型B（周期锁定）：_do_rebalance() 通过 freq_adapter.is_weekly_first_day()
      判断触发时机，无论驱动是 1d 还是 1m，每周只执行一次换仓。
    """
    signals = []

    # ===== 类型A：周期透明 —— 每次 bar 都执行止损止盈检查 =====
    # 确保持仓股票的行情数据在 data 中（1m 驱动时 stock_list 可能不含持仓股）
    _inject_position_prices(data)
    positions = data.get("__positions__", {})
    if positions:
        dt_str = get_data(data, "datetime_str")
        data_keys = [k for k in data.keys() if not k.startswith("__")]
        pos_parts = []
        for sc, info in positions.items():
            avg = info.get("avg_price", 0)
            cur = get_price(data, sc, "open")
            in_data = sc in data_keys
            if cur > 0:
                pnl = (cur - avg) / avg if avg > 0 else 0
                sign = "+" if pnl >= 0 else ""
                pos_parts.append(f"{sc[:6]} 成本{avg:.2f} 现价{cur:.2f} {sign}{pnl:.2%}")
            else:
                pos_parts.append(f"{sc[:6]} 成本{avg:.2f} 现价N/A(in_data={in_data})")
        _log(data, f"[止损检查][{dt_str}] {' | '.join(pos_parts)}", "DEBUG")
    signals.extend(stop_manager.check(data))

    # ===== 类型B：周期锁定 —— 适配器判断是否到了"周级别换仓时机" =====
    if freq_adapter.is_weekly_first_day(data):
        signals.extend(_do_rebalance(data))

    return signals
