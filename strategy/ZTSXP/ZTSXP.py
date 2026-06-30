# coding: utf-8
"""
涨停双响炮策略（ZTSXP）
======================
核心思想：捕捉"历史涨停后经过合法调整、即将再次封板"的强势股。
  - 第一炮：过去 gap_max 个交易日内某日收盘涨停，此后处于合法调整区间
  - 第二炮：监控日盘中再次封板涨停，策略确认信号并买入
  - 退出：止损 / 追踪止盈 / 尾盘未涨停

支持回测模式与实盘模式，通过 _is_live_mode() 隔离副作用。
Mac 平台通过 xtdata_proxy 透明代理访问 Windows VM 上的 xtdata。
"""

from utils.quant_import import *
from types import SimpleNamespace

# ============================================================
# 策略参数
# ============================================================
PARAMS = {
    # ── Scanner 形态参数 ──────────────────────────────────────
    'gap_min':           2,      # 两炮间隔最小天数（含两端，即至少隔 1 个交易日）
    'gap_max':           5,      # 两炮间隔最大天数（含两端，即最多隔 4 个交易日）

    # ── Scanner 选股过滤参数 ──────────────────────────────────
    'market_cap_limit':  200,    # 市值上限（亿元），0 表示不限制
    'min_listing_days':  60,     # 新股过滤：上市不足 N 天的股票排除

    # ── Monitor 止盈止损参数 ──────────────────────────────────
    'stop_loss_pct':     0.03,   # 止损比例（相对买入价）
    'trailing_stop_pct': 0.03,   # 追踪止盈回撤比例（相对历史最高价）

    # ── Monitor 仓位管理参数 ──────────────────────────────────
    'max_positions':     6,      # 最大同时持仓数
    'position_value':    5000,   # 每笔买入金额（元）

    # ── 诊断参数 ─────────────────────────────────────────────
    'verbose_log':       False,  # True 时打印每只股票 K 线明细（诊断用）

    # ── 实盘专用参数 ─────────────────────────────────────────
    'watchlist_group':   'ZTSXP_Seeds',  # QMT 自选股板块名（仅实盘生效）
}

# ============================================================
# 全局状态对象
# ============================================================
g = SimpleNamespace(
    # ── Scanner 侧缓存（init 时预热，后续只读）──────────────────
    stock_name_cache        = {},   # {code: name}
    listing_date_cache      = {},   # {code: 'YYYYMMDD'}
    total_shares_cache      = {},   # {code: total_shares}
    instrument_status_cache = {},   # {code: status}  0=正常
    expire_date_cache       = {},   # {code: expire_date}

    # ── 跨日传递的种子名单 ────────────────────────────────────
    seeds_for_tomorrow      = [],   # on_post_market 写入，on_bar 读取

    # ── Monitor 侧状态 ────────────────────────────────────────
    holdings                = {},   # {code: {buy_price, buy_date, high_price, ztp_price, volume}}
    trades                  = [],   # 交易记录列表
    watchlist               = [],   # 当日监控名单（每日从 seeds_for_tomorrow 加载）
    bought_today            = set(),# 今日已买入集合（防止重复买入）
    last_bar_date           = '',   # 上一根 bar 的日期，用于检测交易日切换
)

# ============================================================
# 辅助函数
# ============================================================

def _is_live_mode(context) -> bool:
    """判断当前是否为实盘模式，异常时安全降级返回 False"""
    try:
        return context['__framework__'].config.run_mode == 'live'
    except Exception:
        return False


def _get_limit_ratio(stock_code: str, stock_name: str) -> float:
    """获取涨跌幅限制比例
    科创板(688x) / 创业板(300x) → 20%
    ST 股 → 5%
    其余 → 10%
    """
    pure_code = stock_code.split('.')[0]
    if pure_code.startswith('688') or pure_code.startswith('300'):
        return 0.20
    if 'ST' in stock_name or 'st' in stock_name:
        return 0.05
    return 0.10


def _calc_limit_price(pre_close: float, limit_ratio: float) -> float:
    """计算涨停价"""
    return round(pre_close * (1 + limit_ratio), 2)


def _get_instrument_detail_field(detail, field: str, default=None):
    """兼容 Mac proxy 返回 dict 和 Windows 返回对象两种格式读取字段"""
    if detail is None:
        return default
    # dict 格式（Mac proxy）
    if isinstance(detail, dict):
        return detail.get(field, default)
    # 对象格式（Windows 原生）
    return getattr(detail, field, default)


def _get_meta_path(context) -> str:
    """获取 _meta.json 文件路径（与策略文件同目录）"""
    try:
        strategy_file = context['__framework__'].config.strategy_file
        return os.path.join(os.path.dirname(strategy_file), '_meta.json')
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '_meta.json')


def _prev_trade_date(date_str: str) -> str:
    """获取指定日期的前一个交易日（YYYYMMDD 格式）"""
    try:
        d = dt.strptime(date_str, '%Y%m%d').date()
        # 向前最多查 10 天
        for i in range(1, 11):
            prev = d - timedelta(days=i)
            if is_trade_day(prev.strftime('%Y-%m-%d')):
                return prev.strftime('%Y%m%d')
    except Exception:
        pass
    return ''


# ============================================================
# init — 全市场缓存预热 + 崩溃恢复
# ============================================================

def init(stock_list, context):
    """策略初始化：预热全市场缓存，实盘模式下尝试从 _meta.json 崩溃恢复"""
    logging.info('[ZTSXP] init 开始')

    # ── 0. 打印当前参数配置（方便复现）──────────────────────────
    logging.info('[ZTSXP] 当前策略参数:')
    for k, v in PARAMS.items():
        logging.info(f'  {k} = {v}')

    # ── 1. 全市场股票信息缓存预热 ──────────────────────────────
    try:
        all_stocks = xtdata.get_stock_list_in_sector('沪深A股')
    except Exception as e:
        logging.error(f'[ZTSXP] 获取全市场股票列表失败: {e}')
        all_stocks = []

    for code in all_stocks:
        try:
            detail = xtdata.get_instrument_detail(code)
            if detail is None:
                continue
            g.stock_name_cache[code]        = _get_instrument_detail_field(detail, 'InstrumentName', '')
            g.listing_date_cache[code]      = str(_get_instrument_detail_field(detail, 'OpenDate', 0))
            g.total_shares_cache[code]      = _get_instrument_detail_field(detail, 'TotalVolume', 0)
            g.instrument_status_cache[code] = _get_instrument_detail_field(detail, 'InstrumentStatus', 0)
            g.expire_date_cache[code]       = _get_instrument_detail_field(detail, 'ExpireDate', 0)
        except Exception:
            continue

    logging.info(f'[ZTSXP] 缓存预热完成，共 {len(g.stock_name_cache)} 只股票')

    # ── 2. 实盘崩溃恢复 ────────────────────────────────────────
    if _is_live_mode(context) and not g.seeds_for_tomorrow:
        meta_path = _get_meta_path(context)
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            scan_date = meta.get('scan_date', '')
            # 获取今日日期，判断 scan_date 是否为昨日交易日
            today_str = dt.now().strftime('%Y%m%d')
            prev_td = _prev_trade_date(today_str)
            if scan_date == prev_td and meta.get('seeds'):
                g.seeds_for_tomorrow = meta['seeds']
                logging.info(f'[ZTSXP] 从 _meta.json 恢复种子名单，共 {len(g.seeds_for_tomorrow)} 只，scan_date={scan_date}')
            else:
                logging.info(f'[ZTSXP] _meta.json 日期不匹配（scan_date={scan_date}, 昨日交易日={prev_td}），跳过恢复')
        except FileNotFoundError:
            logging.info('[ZTSXP] _meta.json 不存在，跳过崩溃恢复')
        except Exception as e:
            logging.warning(f'[ZTSXP] 读取 _meta.json 失败，跳过恢复: {e}')

    # ── 3. 实盘模式下从真实持仓恢复 g.holdings ────────────────
    if _is_live_mode(context):
        try:
            positions = context.get('__positions__', {})
            if positions:
                for code, pos in positions.items():
                    if code not in g.holdings:
                        # 从真实持仓重建 holdings 元数据
                        # buy_price / buy_date / high_price 无法从持仓精确还原，
                        # 使用 avg_price 作为 buy_price，high_price 初始化为 avg_price
                        avg_price = float(pos.get('avg_price', pos.get('open_price', 0)))
                        # 尝试从 _meta.json 中的 holdings 字段恢复（如果有）
                        meta_path = _get_meta_path(context)
                        meta_holdings = {}
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                            meta_holdings = meta.get('holdings', {})
                        except Exception:
                            pass

                        if code in meta_holdings:
                            g.holdings[code] = meta_holdings[code]
                        else:
                            # 无历史记录，用持仓均价兜底
                            g.holdings[code] = {
                                'buy_price':  avg_price,
                                'buy_date':   '',
                                'high_price': avg_price,
                                'ztp_price':  0,
                                'volume':     int(pos.get('volume', 0)),
                            }
                logging.info(f'[ZTSXP] 从真实持仓恢复 g.holdings，共 {len(g.holdings)} 只')
        except Exception as e:
            logging.warning(f'[ZTSXP] 恢复 g.holdings 失败: {e}')

    logging.info('[ZTSXP] init 完成')


# ============================================================
# on_post_market — Scanner 全市场扫描
# ============================================================

def on_post_market(context):
    """盘后扫描全市场，识别第一炮种子股，写入 g.seeds_for_tomorrow"""
    bar_date = context.get('__current_time__', {}).get('date', '')
    if not bar_date:
        logging.warning('[ZTSXP] on_post_market: 无法获取当前日期，跳过')
        return

    # bar_date 格式为 'YYYY-MM-DD'，转为 'YYYYMMDD' 供 get_history 使用
    bar_date_num = bar_date.replace('-', '')

    gap_min           = PARAMS['gap_min']
    gap_max           = PARAMS['gap_max']
    market_cap_limit  = PARAMS['market_cap_limit']
    min_listing_days  = PARAMS['min_listing_days']
    verbose_log       = PARAMS['verbose_log']

    logging.info(f'[ZTSXP] Scanner 开始扫描，基准日={bar_date}')

    # ── 1. 构建候选股票池 ──────────────────────────────────────
    today_dt = dt.strptime(bar_date, '%Y-%m-%d').date()
    candidates = []

    for code in g.stock_name_cache:
        pure_code = code.split('.')[0]

        # 代码前缀过滤（沪深 A 股）
        if not (pure_code.startswith('60') or pure_code.startswith('688')
                or pure_code.startswith('00') or pure_code.startswith('30')):
            continue

        name = g.stock_name_cache.get(code, '')

        # 排除 ST
        if 'ST' in name or 'st' in name:
            continue

        # 排除停牌
        if g.instrument_status_cache.get(code, 0) != 0:
            continue

        # 排除退市（ExpireDate 不为 0 且不为 99999999）
        expire = g.expire_date_cache.get(code, 0)
        try:
            expire_int = int(expire)
            if expire_int != 0 and expire_int != 99999999:
                expire_dt = dt.strptime(str(expire_int), '%Y%m%d').date()
                if expire_dt <= today_dt:
                    continue
        except Exception:
            pass

        # 排除新股（上市不足 min_listing_days 天）
        open_date_str = g.listing_date_cache.get(code, '0')
        try:
            open_date_int = int(open_date_str)
            if open_date_int <= 0 or open_date_int < 19900101:
                continue  # 无效上市日期（新股申购、配股等）
            open_dt = dt.strptime(str(open_date_int), '%Y%m%d').date()
            if (today_dt - open_dt).days < min_listing_days:
                continue
        except Exception:
            continue

        candidates.append(code)

    logging.info(f'[ZTSXP] 候选股票池：{len(candidates)} 只')

    # ── 2. 分批获取日线数据，执行种子识别 ──────────────────────
    seeds = []
    batch_size = 500

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        try:
            batch_data = get_history(
                symbol_list=batch,
                fields=['close', 'preClose'],
                bar_count=gap_max + 2,
                fre_step='1d',
                current_time=bar_date_num
            )
        except Exception as e:
            logging.warning(f'[ZTSXP] get_history 批次 {i//batch_size} 失败: {e}')
            continue

        for code in batch:
            df = batch_data.get(code)
            if df is None or df.empty or len(df) < 2:
                continue

            name = g.stock_name_cache.get(code, '')
            limit_ratio = _get_limit_ratio(code, name)

            closes     = df['close'].tolist()
            pre_closes = df['preClose'].tolist()
            n = len(closes)
            today_idx = n - 1  # 最后一根 bar 为当日

            if verbose_log:
                logging.debug(f'[ZTSXP] {code} {name} closes={closes}')

            # ── 步骤1：找最近涨停日（第一炮）──────────────────
            first_bar = -1
            for j in range(today_idx - 1, -1, -1):
                lp = _calc_limit_price(pre_closes[j], limit_ratio)
                if closes[j] >= lp:
                    first_bar = j
                    break

            if first_bar < 0:
                continue  # 无涨停日

            # ── 步骤2：间隔天数校验 ────────────────────────────
            gap = today_idx - first_bar  # 间隔 bar 数
            if not (gap_min - 1 <= gap <= gap_max - 1):
                continue  # 间隔不符

            # ── 步骤3：今日未涨停 ──────────────────────────────
            today_lp = _calc_limit_price(pre_closes[today_idx], limit_ratio)
            if closes[today_idx] >= today_lp:
                continue  # 今日已涨停，第二炮已发生

            # ── 步骤4：调整区间合法性 ──────────────────────────
            first_limit_price = _calc_limit_price(pre_closes[first_bar], limit_ratio)
            first_pre_close   = pre_closes[first_bar]
            range_ok = True
            for k in range(first_bar + 1, today_idx + 1):
                c = closes[k]
                if c < first_pre_close or c > first_limit_price:
                    range_ok = False
                    break
            if not range_ok:
                continue

            # ── 步骤5：通过，写入种子列表 ──────────────────────
            # 预期第二炮涨停价（基于今日收盘价计算）
            expected_second_lp = _calc_limit_price(closes[today_idx], limit_ratio)

            # 第一炮日期：从 df 的 time 列获取
            try:
                first_date_str = df['time'].iloc[first_bar].strftime('%Y%m%d')
            except Exception:
                first_date_str = ''

            seeds.append({
                'code':                        code,
                'name':                        name,
                'first_date':                  first_date_str,
                'first_limit_price':           first_limit_price,
                'gap_days_so_far':             gap,
                'expected_second_limit_price': expected_second_lp,
                'today_close':                 closes[today_idx],
            })

    # ── 3. 按间隔天数降序排列，写入内存 ───────────────────────
    seeds.sort(key=lambda s: s['gap_days_so_far'], reverse=True)
    g.seeds_for_tomorrow = seeds

    # ── 过滤漏斗统计 ───────────────────────────────────────────
    total_market = len(g.stock_name_cache)
    after_prefix = len([c for c in g.stock_name_cache
                        if c.split('.')[0].startswith(('60', '688', '00', '30'))])
    logging.info(
        f'[ZTSXP] Scanner 完成 | 基准日={bar_date}\n'
        f'  全市场缓存: {total_market} 只\n'
        f'  代码前缀过滤后: {after_prefix} 只\n'
        f'  候选（排除ST/停牌/退市/新股）: {len(candidates)} 只\n'
        f'  通过形态识别（种子股）: {len(seeds)} 只'
    )
    if seeds:
        logging.info('[ZTSXP] 种子股明细:')
        for s in seeds:
            logging.info(
                f"  {s['code']} {s['name']} | 第一炮={s['first_date']} "
                f"间隔={s['gap_days_so_far']}天 "
                f"预期涨停价={s['expected_second_limit_price']:.2f}"
            )

    # ── 4. 实盘副作用 ──────────────────────────────────────────
    if _is_live_mode(context):
        # 4a. 写入 _meta.json（崩溃恢复用）
        meta_path = _get_meta_path(context)
        try:
            meta = {
                'scan_date': bar_date_num,
                'seeds':     seeds,
                'holdings':  g.holdings,   # 持仓元数据，供重启后恢复 g.holdings
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            logging.info(f'[ZTSXP] _meta.json 写入成功: {meta_path}')
        except Exception as e:
            logging.error(f'[ZTSXP] _meta.json 写入失败: {e}')

        # 4b. 写入 QMT 自选股板块（界面可视化查看）
        watchlist_group = PARAMS['watchlist_group']
        seed_codes = [s['code'] for s in seeds]
        if hasattr(xtdata, 'set_stock_list_in_sector'):
            try:
                xtdata.set_stock_list_in_sector(watchlist_group, seed_codes)
                logging.info(f'[ZTSXP] QMT 板块 "{watchlist_group}" 写入 {len(seed_codes)} 只')
            except Exception as e:
                logging.error(f'[ZTSXP] QMT 板块写入失败: {e}')
        else:
            logging.warning(
                f'[ZTSXP] xtdata 不支持 set_stock_list_in_sector（Mac proxy 限制），'
                f'跳过板块写入，种子名单已保存到 _meta.json'
            )


# ============================================================
# on_bar — Monitor 盘中监控
# ============================================================

def on_bar(context):
    """每根 1m bar 触发：持仓管理 + 第二炮买入信号"""
    signals = []

    current_time_info = context.get('__current_time__', {})
    bar_date = current_time_info.get('date', '')   # 'YYYY-MM-DD'
    bar_time = current_time_info.get('time', '')   # 'HH:MM:SS'

    if not bar_date:
        return signals

    # ── 新交易日检测 ───────────────────────────────────────────
    if bar_date != g.last_bar_date:
        g.bought_today  = set()
        g.watchlist     = [s['code'] for s in g.seeds_for_tomorrow]
        # 建立当日涨停价映射 {code: expected_second_limit_price}
        g._today_limit_prices = {
            s['code']: s['expected_second_limit_price']
            for s in g.seeds_for_tomorrow
        }
        g.last_bar_date = bar_date
        logging.info(f'[ZTSXP] 新交易日 {bar_date}，监控名单 {len(g.watchlist)} 只')

    # ── 卖出逻辑 ───────────────────────────────────────────────
    sell_signals = _handle_sell(context, bar_date, bar_time)
    signals.extend(sell_signals)

    # ── 买入逻辑 ───────────────────────────────────────────────
    buy_signals = _handle_buy(context, bar_date)
    signals.extend(buy_signals)

    return signals


def _handle_sell(context, bar_date: str, bar_time: str) -> list:
    """卖出逻辑：止损 > 追踪止盈 > 尾盘未涨停"""
    signals = []
    stop_loss_pct     = PARAMS['stop_loss_pct']
    trailing_stop_pct = PARAMS['trailing_stop_pct']

    to_sell = []  # 避免遍历时修改字典

    for code, holding in list(g.holdings.items()):
        # T+1 保护：当日买入不当日卖出
        if holding.get('buy_date') == bar_date:
            continue

        # 获取当前价格
        close = get_price(context, code, 'close')
        if close <= 0:
            continue

        # 更新最高价
        if close > holding['high_price']:
            holding['high_price'] = close

        buy_price   = holding['buy_price']
        high_price  = holding['high_price']
        ztp_price   = holding['ztp_price']
        sell_reason = None

        # 规则1：止损
        if close <= buy_price * (1 - stop_loss_pct):
            sell_reason = '止损'
        # 规则2：追踪止盈
        elif close <= high_price * (1 - trailing_stop_pct):
            sell_reason = '追踪止盈'
        # 规则3：尾盘未涨停
        elif bar_time >= '14:50:00' and close < ztp_price:
            sell_reason = '尾盘未涨停'

        if sell_reason:
            to_sell.append((code, close, holding['volume'], sell_reason))

    for code, close, volume, reason in to_sell:
        sig = generate_signal(context, code, close, 1.0, 'sell', reason)
        if sig:
            signals.extend(sig)
            # 从持仓删除，写入交易记录
            holding = g.holdings.pop(code, {})
            buy_price = holding.get('buy_price', 0)
            buy_date  = holding.get('buy_date', '')
            name      = g.stock_name_cache.get(code, code)

            # 计算持仓天数
            hold_days = 0
            try:
                if buy_date:
                    buy_dt   = dt.strptime(buy_date, '%Y-%m-%d').date()
                    sell_dt  = dt.strptime(bar_date, '%Y-%m-%d').date()
                    hold_days = (sell_dt - buy_dt).days
            except Exception:
                pass

            # 计算收益率
            pnl_pct = (close - buy_price) / buy_price * 100 if buy_price > 0 else 0

            g.trades.append({
                'code':       code,
                'action':     'sell',
                'price':      close,
                'volume':     volume,
                'reason':     reason,
                'sell_date':  bar_date,
                'buy_price':  buy_price,
                'buy_date':   buy_date,
                'hold_days':  hold_days,
                'pnl_pct':    pnl_pct,
            })
            logging.info(
                f'[ZTSXP] 卖出 {code} {name} | 原因={reason} | '
                f'卖出价={close:.2f} | 买入价={buy_price:.2f} | '
                f'持仓天数={hold_days}天 | 收益率={pnl_pct:+.2f}%'
            )

    return signals


def _handle_buy(context, bar_date: str) -> list:
    """买入逻辑：检测第二炮（close ≥ up_stop_price）"""
    signals = []

    max_positions  = PARAMS['max_positions']
    position_value = PARAMS['position_value']

    # 前置检查
    positions = context.get('__positions__', {})
    if len(positions) >= max_positions:
        return signals
    if not g.watchlist:
        return signals

    today_limit_prices = getattr(g, '_today_limit_prices', {})

    for code in g.watchlist:
        # 持仓数量再次检查（可能在本轮已买入多只）
        if len(positions) + len([s for s in signals if s.get('action') == 'buy']) >= max_positions:
            break

        # 不在持仓中
        if code in positions:
            continue

        # 今日未买过
        if code in g.bought_today:
            continue

        # 获取当前价格
        close = get_price(context, code, 'close')
        if close <= 0:
            continue

        # 第二炮确认：close ≥ 涨停价
        up_stop_price = today_limit_prices.get(code, 0)
        if up_stop_price <= 0 or close < up_stop_price:
            continue

        # 计算买入数量（向下取整到 100 股，最少 100 股）
        volume = int(position_value / close / 100) * 100
        volume = max(volume, 100)

        # 生成买入信号（ratio > 1 时表示指定股数）
        sig = generate_signal(context, code, close, float(volume), 'buy', '涨停双响炮第二炮')
        if sig:
            signals.extend(sig)
            # 写入持仓元数据
            g.holdings[code] = {
                'buy_price':  close,
                'buy_date':   bar_date,
                'high_price': close,
                'ztp_price':  up_stop_price,
                'volume':     volume,
            }
            g.bought_today.add(code)
            name = g.stock_name_cache.get(code, code)
            logging.info(
                f'[ZTSXP] 买入 {code} {name} | '
                f'买入价={close:.2f} | 数量={volume}股 | 涨停价={up_stop_price:.2f}'
            )

    return signals
