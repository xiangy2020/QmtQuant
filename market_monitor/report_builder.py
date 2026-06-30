"""
report_builder.py — HTML 报告生成器

将三大分析模块的结果整合为一个独立的 HTML 文件：
  - Tab 1：市场全景扫描（大盘指数 + 涨跌分布 + 量能 + 新高新低）
  - Tab 2：涨停板/个股异动监控（涨停 / 跌停 / 炸板 / 量价异动）
  - Tab 3：行业板块轮动分析（申万一级行业排名）

特性：
  - 纯 HTML + CSS + JavaScript，不依赖外部 CDN，离线可用
  - 涨红跌绿数字高亮
  - 表格点击列头排序
  - 热点行业高亮显示（涨停数最多前3个）
  - 报告顶部显示生成时间和数据日期
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认输出目录
_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "dashboard"


class ReportBuilder:
    """
    HTML 报告生成器。

    build() 方法接收三大模块的分析结果，生成完整的 HTML 报告文件。
    """

    def build(
        self,
        trade_date: str,
        overview_data: Optional[Dict] = None,
        limit_up_data: Optional[Dict] = None,
        sector_data: Optional[Dict] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        生成 HTML 报告。

        Args:
            trade_date:    分析日期 YYYYMMDD
            overview_data: 市场全景扫描结果（可为 None）
            limit_up_data: 涨停板监控结果（可为 None）
            sector_data:   行业轮动分析结果（可为 None）
            output_path:   输出路径（不指定则默认 dashboard/market_report_{date}.html）

        Returns:
            HTML 文件的绝对路径字符串
        """
        # 确定输出路径
        if output_path:
            out_path = Path(output_path)
        else:
            _DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = _DEFAULT_OUTPUT_DIR / f"market_report_{trade_date}.html"

        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 生成 HTML 内容
        html = self._render_html(trade_date, overview_data, limit_up_data, sector_data)

        # 写入文件
        out_path.write_text(html, encoding='utf-8')
        logger.info(f"[ReportBuilder] HTML 报告已写入：{out_path}")
        return str(out_path)

    # ──────────────────────────────────────────────────────────────
    # HTML 渲染主入口
    # ──────────────────────────────────────────────────────────────

    def _render_html(
        self,
        trade_date: str,
        overview_data: Optional[Dict],
        limit_up_data: Optional[Dict],
        sector_data: Optional[Dict],
    ) -> str:
        gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        date_display = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

        # 各 Tab 内容
        tab1_content = self._render_overview_tab(overview_data)
        tab2_content = self._render_limit_up_tab(limit_up_data)
        tab3_content = self._render_sector_tab(sector_data)

        # 动态 Tab 导航：有数据的 Tab 正常显示，无数据的 Tab 灰色禁用
        has_overview  = overview_data  is not None
        has_limit_up  = limit_up_data  is not None
        has_sector    = sector_data    is not None

        # 确定默认激活的 Tab（第一个有数据的）
        if has_overview:
            default_tab = 'overview'
        elif has_limit_up:
            default_tab = 'limitup'
        elif has_sector:
            default_tab = 'sector'
        else:
            default_tab = 'overview'

        def _tab_btn(tab_id: str, label: str, has_data: bool) -> str:
            if has_data:
                active = 'active' if tab_id == default_tab else ''
                return f'<button class="tab-btn {active}" onclick="switchTab(\'{tab_id}\')">'\
                       f'{label}</button>'
            else:
                return f'<button class="tab-btn tab-btn-disabled" disabled title="本次未运行此模块，'\
                       f'使用 --type all 可同时生成全部模块">{label} <span class="tab-na">(未运行)</span></button>'

        tab_btn1 = _tab_btn('overview', '🌐 市场全景', has_overview)
        tab_btn2 = _tab_btn('limitup',  '🚀 涨停监控', has_limit_up)
        tab_btn3 = _tab_btn('sector',   '🏭 行业轮动', has_sector)

        # 默认激活的 Tab content
        def _tab_div(tab_id: str, content: str) -> str:
            active = 'active' if tab_id == default_tab else ''
            return f'<div id="tab-{tab_id}" class="tab-content {active}">\n{content}\n</div>'

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>市场行情监控报告 {date_display}</title>
<style>
{self._get_css()}
</style>
</head>
<body>
<div class="header">
  <h1>📊 市场行情监控报告</h1>
  <div class="meta">
    <span class="date-badge">数据日期：{date_display}</span>
    <span class="gen-time">生成时间：{gen_time}</span>
  </div>
</div>

<div class="tab-bar">
  {tab_btn1}
  {tab_btn2}
  {tab_btn3}
</div>

{_tab_div('overview', tab1_content)}
{_tab_div('limitup',  tab2_content)}
{_tab_div('sector',   tab3_content)}

<script>
{self._get_js()}
</script>
</body>
</html>"""

    # ──────────────────────────────────────────────────────────────
    # Tab 1：市场全景扫描
    # ──────────────────────────────────────────────────────────────

    def _render_overview_tab(self, data: Optional[Dict]) -> str:
        if not data:
            return '<div class="no-data">本次未运行市场全景扫描模块<br><span style="font-size:11px">使用 <code>--type overview</code> 或 <code>--type all</code> 可生成此模块数据</span></div>'

        indices_html  = self._render_indices(data.get('indices', []))
        breadth_html  = self._render_breadth(data.get('breadth', {}))
        turnover_html = self._render_turnover(data.get('turnover', {}))
        high_low_html = self._render_high_low(data.get('high_low', {}))

        return f"""
<div class="section-grid">
  <div class="section full-width">
    <h2>📈 大盘指数</h2>
    {indices_html}
  </div>
</div>
<div class="section-grid three-col">
  <div class="section">
    <h2>📊 涨跌分布</h2>
    {breadth_html}
  </div>
  <div class="section">
    <h2>💰 量能分析</h2>
    {turnover_html}
  </div>
  <div class="section">
    <h2>🏔️ 新高新低</h2>
    {high_low_html}
  </div>
</div>"""

    def _render_indices(self, indices: List[Dict]) -> str:
        if not indices:
            return '<div class="no-data">指数数据不可用</div>'

        rows = ''
        for idx in indices:
            if idx.get('missing'):
                rows += f"""<tr>
  <td>{idx['name']}</td><td class="code">{idx['symbol']}</td>
  <td colspan="7" class="missing">数据缺失</td>
</tr>"""
            else:
                pct = idx.get('pct_chg')
                pct_cls = _pct_class(pct)
                pct_str = _fmt_pct(pct)
                rows += f"""<tr>
  <td><strong>{idx['name']}</strong></td>
  <td class="code">{idx['symbol']}</td>
  <td>{_fmt_num(idx.get('open'))}</td>
  <td>{_fmt_num(idx.get('high'))}</td>
  <td>{_fmt_num(idx.get('low'))}</td>
  <td><strong>{_fmt_num(idx.get('close'))}</strong></td>
  <td class="{pct_cls}"><strong>{pct_str}</strong></td>
  <td>{_fmt_vol(idx.get('volume'))}</td>
  <td>{_fmt_amount(idx.get('amount'))}</td>
</tr>"""

        return f"""<table class="data-table sortable" id="tbl-indices">
<thead><tr>
  <th>名称</th><th>代码</th><th>开盘</th><th>最高</th><th>最低</th>
  <th>收盘</th><th>涨跌幅</th><th>成交量</th><th>成交额</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _render_breadth(self, breadth: Dict) -> str:
        if not breadth:
            return '<div class="no-data">数据不可用</div>'

        total      = breadth.get('total', 0)
        up         = breadth.get('up', 0)
        down       = breadth.get('down', 0)
        flat       = breadth.get('flat', 0)
        limit_up   = breadth.get('limit_up', 0)
        limit_down = breadth.get('limit_down', 0)

        up_pct   = round(up   / total * 100, 1) if total else 0
        down_pct = round(down / total * 100, 1) if total else 0

        return f"""<div class="stat-grid">
  <div class="stat-item up">
    <div class="stat-val">{up}</div>
    <div class="stat-lbl">上涨 ({up_pct}%)</div>
  </div>
  <div class="stat-item down">
    <div class="stat-val">{down}</div>
    <div class="stat-lbl">下跌 ({down_pct}%)</div>
  </div>
  <div class="stat-item flat">
    <div class="stat-val">{flat}</div>
    <div class="stat-lbl">平盘</div>
  </div>
  <div class="stat-item limit-up">
    <div class="stat-val">{limit_up}</div>
    <div class="stat-lbl">涨停</div>
  </div>
  <div class="stat-item limit-down">
    <div class="stat-val">{limit_down}</div>
    <div class="stat-lbl">跌停</div>
  </div>
  <div class="stat-item total">
    <div class="stat-val">{total}</div>
    <div class="stat-lbl">参与统计</div>
  </div>
</div>"""

    def _render_turnover(self, turnover: Dict) -> str:
        if not turnover:
            return '<div class="no-data">数据不可用</div>'

        today    = turnover.get('today')
        avg5d    = turnover.get('avg_5d')
        avg20d   = turnover.get('avg_20d')
        ratio5d  = turnover.get('ratio_5d')
        ratio20d = turnover.get('ratio_20d')

        ratio20d_cls = 'up' if ratio20d and ratio20d >= 1 else 'down'

        return f"""<div class="kv-list">
  <div class="kv-row">
    <span class="kv-key">今日成交额</span>
    <span class="kv-val"><strong>{_fmt_yi(today)}</strong></span>
  </div>
  <div class="kv-row">
    <span class="kv-key">近5日均值</span>
    <span class="kv-val">{_fmt_yi(avg5d)}</span>
  </div>
  <div class="kv-row">
    <span class="kv-key">近20日均值</span>
    <span class="kv-val">{_fmt_yi(avg20d)}</span>
  </div>
  <div class="kv-row">
    <span class="kv-key">量能比(5日)</span>
    <span class="kv-val {_pct_class(ratio5d - 1 if ratio5d else None)}">{_fmt_ratio(ratio5d)}</span>
  </div>
  <div class="kv-row">
    <span class="kv-key">量能比(20日)</span>
    <span class="kv-val {ratio20d_cls}"><strong>{_fmt_ratio(ratio20d)}</strong></span>
  </div>
</div>"""

    def _render_high_low(self, high_low: Dict) -> str:
        if not high_low:
            return '<div class="no-data">数据不可用</div>'

        return f"""<div class="kv-list">
  <div class="kv-row">
    <span class="kv-key">20日新高</span>
    <span class="kv-val up">{high_low.get('new_high_20', 0)}</span>
    <span class="kv-sep">/</span>
    <span class="kv-val down">{high_low.get('new_low_20', 0)}</span>
    <span class="kv-key">新低</span>
  </div>
  <div class="kv-row">
    <span class="kv-key">60日新高</span>
    <span class="kv-val up">{high_low.get('new_high_60', 0)}</span>
    <span class="kv-sep">/</span>
    <span class="kv-val down">{high_low.get('new_low_60', 0)}</span>
    <span class="kv-key">新低</span>
  </div>
  <div class="kv-row">
    <span class="kv-key">250日新高</span>
    <span class="kv-val up">{high_low.get('new_high_250', 0)}</span>
    <span class="kv-sep">/</span>
    <span class="kv-val down">{high_low.get('new_low_250', 0)}</span>
    <span class="kv-key">新低</span>
  </div>
</div>"""

    # ──────────────────────────────────────────────────────────────
    # Tab 2：涨停板/个股异动监控
    # ──────────────────────────────────────────────────────────────

    def _render_limit_up_tab(self, data: Optional[Dict]) -> str:
        if not data:
            return '<div class="no-data">本次未运行涨停板监控模块<br><span style="font-size:11px">使用 <code>--type limit-up</code> 或 <code>--type all</code> 可生成此模块数据</span></div>'

        limit_up_html    = self._render_limit_up_table(data.get('limit_up', []))
        limit_down_html  = self._render_limit_down_table(data.get('limit_down', []))
        broken_html      = self._render_broken_limit_table(data.get('broken_limit', []))
        surge_html       = self._render_volume_surge_table(data.get('volume_surge', []))

        return f"""
<div class="section-grid two-col">
  <div class="section">
    <h2>🚀 涨停股 ({len(data.get('limit_up', []))}只)</h2>
    {limit_up_html}
  </div>
  <div class="section">
    <h2>📉 跌停股 ({len(data.get('limit_down', []))}只)</h2>
    {limit_down_html}
  </div>
</div>
<div class="section-grid two-col">
  <div class="section">
    <h2>💥 炸板股 ({len(data.get('broken_limit', []))}只)</h2>
    {broken_html}
  </div>
  <div class="section">
    <h2>⚡ 量价异动 ({len(data.get('volume_surge', []))}只)</h2>
    {surge_html}
  </div>
</div>"""

    def _render_limit_up_table(self, items: List[Dict]) -> str:
        if not items:
            return '<div class="no-data">今日无涨停股</div>'
        rows = ''
        for item in items:
            consec = item.get('consec_days', 1)
            consec_badge = f'<span class="badge badge-hot">{consec}连板</span>' if consec > 1 else ''
            rows += f"""<tr>
  <td class="code">{item['symbol']}</td>
  <td>{item['name']}{consec_badge}</td>
  <td>{item.get('industry', '—')}</td>
  <td class="up"><strong>{_fmt_pct(item.get('pct_chg'))}</strong></td>
  <td>{_fmt_wan(item.get('amount'))}万</td>
  <td data-val="{consec}">{consec}</td>
</tr>"""
        return f"""<table class="data-table sortable" id="tbl-limit-up">
<thead><tr>
  <th>代码</th><th>名称</th><th>行业</th><th>涨跌幅</th><th>成交额</th><th>连板</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _render_limit_down_table(self, items: List[Dict]) -> str:
        if not items:
            return '<div class="no-data">今日无跌停股</div>'
        rows = ''
        for item in items:
            rows += f"""<tr>
  <td class="code">{item['symbol']}</td>
  <td>{item['name']}</td>
  <td>{item.get('industry', '—')}</td>
  <td class="down"><strong>{_fmt_pct(item.get('pct_chg'))}</strong></td>
  <td>{_fmt_wan(item.get('amount'))}万</td>
</tr>"""
        return f"""<table class="data-table sortable" id="tbl-limit-down">
<thead><tr>
  <th>代码</th><th>名称</th><th>行业</th><th>涨跌幅</th><th>成交额</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _render_broken_limit_table(self, items: List[Dict]) -> str:
        if not items:
            return '<div class="no-data">今日无炸板股</div>'
        rows = ''
        for item in items:
            rows += f"""<tr>
  <td class="code">{item['symbol']}</td>
  <td>{item['name']}</td>
  <td>{item.get('industry', '—')}</td>
  <td class="up">{_fmt_pct(item.get('pct_chg'))}</td>
  <td>{_fmt_num(item.get('high'))}</td>
  <td>{_fmt_num(item.get('close'))}</td>
</tr>"""
        return f"""<table class="data-table sortable" id="tbl-broken">
<thead><tr>
  <th>代码</th><th>名称</th><th>行业</th><th>涨跌幅</th><th>最高价</th><th>收盘价</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _render_volume_surge_table(self, items: List[Dict]) -> str:
        if not items:
            return '<div class="no-data">今日无量价异动股</div>'
        rows = ''
        for item in items:
            rows += f"""<tr>
  <td class="code">{item['symbol']}</td>
  <td>{item['name']}</td>
  <td>{item.get('industry', '—')}</td>
  <td class="{_pct_class(item.get('pct_chg'))}">{_fmt_pct(item.get('pct_chg'))}</td>
  <td class="up"><strong>{item.get('vol_ratio', '—')}x</strong></td>
  <td>{_fmt_wan(item.get('amount'))}万</td>
</tr>"""
        return f"""<table class="data-table sortable" id="tbl-surge">
<thead><tr>
  <th>代码</th><th>名称</th><th>行业</th><th>涨跌幅</th><th>量比</th><th>成交额</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""

    # ──────────────────────────────────────────────────────────────
    # Tab 3：行业板块轮动分析
    # ──────────────────────────────────────────────────────────────

    # 分类前缀 → 显示名称映射
    _CLASSIFICATION_LABELS = {
        'SW1':   '申万一级行业',
        'SW2':   '申万二级行业',
        'SW3':   '申万三级行业',
        'CSRC1': '证监会一级行业',
        'CSRC2': '证监会二级行业',
    }

    def _render_sector_tab(self, data: Optional[Dict]) -> str:
        if not data:
            return '<div class="no-data">本次未运行行业轮动分析模块<br><span style="font-size:11px">使用 <code>--type sector</code> 或 <code>--type all</code> 可生成此模块数据</span></div>'

        sectors        = data.get('sectors', [])
        hot_set        = set(data.get('hot_sectors', []))
        classification = data.get('classification', 'SW1')
        cls_label      = self._CLASSIFICATION_LABELS.get(classification, classification)

        if not sectors:
            return '<div class="no-data">无行业数据</div>'

        rows = ''
        for s in sectors:
            is_hot   = s.get('is_hot', False)
            row_cls  = 'hot-row' if is_hot else ''
            hot_mark = ' 🔥' if is_hot else ''

            rows += f"""<tr class="{row_cls}">
  <td><strong>{s['name']}{hot_mark}</strong></td>
  <td class="{_pct_class(s.get('pct_chg_1d'))}"><strong>{_fmt_pct(s.get('pct_chg_1d'))}</strong></td>
  <td class="{_pct_class(s.get('pct_chg_5d'))}">{_fmt_pct(s.get('pct_chg_5d'))}</td>
  <td class="{_pct_class(s.get('pct_chg_10d'))}">{_fmt_pct(s.get('pct_chg_10d'))}</td>
  <td class="{_pct_class(s.get('pct_chg_20d'))}">{_fmt_pct(s.get('pct_chg_20d'))}</td>
  <td class="up">{s.get('up_count', 0)}</td>
  <td class="down">{s.get('down_count', 0)}</td>
  <td class="limit-up-cell">{s.get('limit_up', 0)}</td>
  <td class="limit-down-cell">{s.get('limit_down', 0)}</td>
  <td>{s.get('total', 0)}</td>
  <td>{_fmt_yi(s.get('amount_today'))}</td>
  <td class="{_pct_class(s.get('amount_ratio', 1) - 1 if s.get('amount_ratio') else None)}">{_fmt_ratio(s.get('amount_ratio'))}</td>
</tr>"""

        hot_names = [s['name'] for s in sectors if s.get('is_hot')]
        hot_tip = f'热点行业：{"、".join(hot_names)}' if hot_names else ''

        return f"""
<div class="section">
  <h2>🏭 {cls_label}轮动排名</h2>
  {f'<div class="hot-tip">🔥 {hot_tip}</div>' if hot_tip else ''}
  <table class="data-table sortable" id="tbl-sector">
  <thead><tr>
    <th>行业</th>
    <th>今日涨跌</th><th>近5日</th><th>近10日</th><th>近20日</th>
    <th>上涨</th><th>下跌</th><th>涨停</th><th>跌停</th><th>成分股</th>
    <th>成交额(亿)</th><th>量能比</th>
  </tr></thead>
  <tbody>{rows}</tbody>
  </table>
</div>"""

    # ──────────────────────────────────────────────────────────────
    # CSS
    # ──────────────────────────────────────────────────────────────

    def _get_css(self) -> str:
        return """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #c9d1d9; font-size: 13px; }
.header { padding: 20px 24px 12px; border-bottom: 1px solid #21262d; }
.header h1 { font-size: 20px; color: #f0f6fc; margin-bottom: 8px; }
.meta { display: flex; gap: 16px; align-items: center; }
.date-badge { background: #1f6feb; color: #fff; padding: 3px 10px;
              border-radius: 12px; font-size: 12px; font-weight: 600; }
.gen-time { color: #8b949e; font-size: 12px; }

/* Tab 导航 */
.tab-bar { display: flex; gap: 4px; padding: 12px 24px 0;
           border-bottom: 1px solid #21262d; }
.tab-btn { background: none; border: none; color: #8b949e; padding: 8px 16px;
           cursor: pointer; font-size: 13px; border-radius: 6px 6px 0 0;
           border-bottom: 2px solid transparent; transition: all .2s; }
.tab-btn:hover { color: #c9d1d9; background: #161b22; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #1f6feb;
                  background: #161b22; font-weight: 600; }
.tab-content { display: none; padding: 20px 24px; }
.tab-content.active { display: block; }

/* 布局 */
.section-grid { display: grid; gap: 16px; margin-bottom: 16px; }
.section-grid.three-col { grid-template-columns: repeat(3, 1fr); }
.section-grid.two-col   { grid-template-columns: repeat(2, 1fr); }
.section-grid.full-width { grid-template-columns: 1fr; }
.full-width { grid-column: 1 / -1; }
.section { background: #161b22; border: 1px solid #21262d;
           border-radius: 8px; padding: 16px; }
.section h2 { font-size: 14px; color: #f0f6fc; margin-bottom: 12px;
              padding-bottom: 8px; border-bottom: 1px solid #21262d; }

/* 表格 */
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { background: #0d1117; color: #8b949e; padding: 7px 10px;
                 text-align: left; border-bottom: 1px solid #21262d;
                 cursor: pointer; user-select: none; white-space: nowrap; }
.data-table th:hover { color: #58a6ff; }
.data-table th.sort-asc::after  { content: ' ▲'; color: #58a6ff; }
.data-table th.sort-desc::after { content: ' ▼'; color: #58a6ff; }
.data-table td { padding: 6px 10px; border-bottom: 1px solid #161b22;
                 white-space: nowrap; }
.data-table tr:hover td { background: #1c2128; }
.data-table tr:last-child td { border-bottom: none; }
.code { color: #79c0ff; font-family: monospace; }
.missing { color: #6e7681; font-style: italic; text-align: center; }

/* 涨跌颜色 */
.up         { color: #f85149; }
.down       { color: #3fb950; }
.flat       { color: #8b949e; }
.limit-up-cell  { color: #ff7b72; font-weight: 600; }
.limit-down-cell { color: #56d364; font-weight: 600; }

/* 统计卡片 */
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.stat-item { background: #0d1117; border-radius: 6px; padding: 10px;
             text-align: center; border: 1px solid #21262d; }
.stat-val { font-size: 22px; font-weight: 700; line-height: 1.2; }
.stat-lbl { font-size: 11px; color: #8b949e; margin-top: 2px; }
.stat-item.up .stat-val         { color: #f85149; }
.stat-item.down .stat-val       { color: #3fb950; }
.stat-item.flat .stat-val       { color: #8b949e; }
.stat-item.limit-up .stat-val   { color: #ff7b72; }
.stat-item.limit-down .stat-val { color: #56d364; }
.stat-item.total .stat-val      { color: #79c0ff; }

/* KV 列表 */
.kv-list { display: flex; flex-direction: column; gap: 8px; }
.kv-row  { display: flex; align-items: center; gap: 6px;
           padding: 6px 8px; background: #0d1117; border-radius: 4px; }
.kv-key  { color: #8b949e; flex: 1; }
.kv-val  { font-weight: 600; min-width: 60px; text-align: right; }
.kv-sep  { color: #6e7681; }

/* 徽章 */
.badge { display: inline-block; padding: 1px 6px; border-radius: 10px;
         font-size: 10px; font-weight: 600; margin-left: 4px; }
.badge-hot { background: #ff7b72; color: #0d1117; }

/* 热点行业 */
.hot-row td { background: rgba(255, 123, 114, 0.08) !important; }
.hot-tip { background: rgba(255, 123, 114, 0.12); border: 1px solid rgba(255, 123, 114, 0.3);
           border-radius: 6px; padding: 8px 12px; margin-bottom: 12px;
           color: #ff7b72; font-size: 12px; }

/* 无数据 */
.no-data { color: #6e7681; text-align: center; padding: 40px 24px;
           font-style: italic; line-height: 2; }
.no-data code { font-style: normal; background: #1c2128; color: #79c0ff;
                padding: 1px 6px; border-radius: 4px; font-family: monospace; }

/* Tab 禁用状态 */
.tab-btn.tab-btn-disabled { color: #484f58; cursor: not-allowed; border-bottom-color: transparent; }
.tab-btn.tab-btn-disabled:hover { color: #484f58; background: none; }
.tab-na { font-size: 10px; color: #6e7681; font-weight: normal; }

/* 响应式 */
@media (max-width: 900px) {
  .section-grid.three-col { grid-template-columns: 1fr; }
  .section-grid.two-col   { grid-template-columns: 1fr; }
}}"""

    # ──────────────────────────────────────────────────────────────
    # JavaScript
    # ──────────────────────────────────────────────────────────────

    def _get_js(self) -> str:
        return """
// Tab 切换
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}

// 表格排序
document.querySelectorAll('table.sortable').forEach(function(table) {
  var headers = table.querySelectorAll('thead th');
  var sortState = {};

  headers.forEach(function(th, colIdx) {
    th.addEventListener('click', function() {
      var asc = sortState[colIdx] !== true;
      sortState = {};
      sortState[colIdx] = asc;

      headers.forEach(function(h) {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');

      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));

      rows.sort(function(a, b) {
        var aCell = a.querySelectorAll('td')[colIdx];
        var bCell = b.querySelectorAll('td')[colIdx];
        if (!aCell || !bCell) return 0;

        // 优先使用 data-val 属性
        var aRaw = aCell.getAttribute('data-val') || aCell.textContent.trim();
        var bRaw = bCell.getAttribute('data-val') || bCell.textContent.trim();

        // 尝试数字比较（去掉 %、x、亿、万 等单位）
        var aNum = parseFloat(aRaw.replace(/[^\\d.\\-]/g, ''));
        var bNum = parseFloat(bRaw.replace(/[^\\d.\\-]/g, ''));

        if (!isNaN(aNum) && !isNaN(bNum)) {
          return asc ? aNum - bNum : bNum - aNum;
        }
        return asc ? aRaw.localeCompare(bRaw, 'zh') : bRaw.localeCompare(aRaw, 'zh');
      });

      rows.forEach(function(row) { tbody.appendChild(row); });
    });
  });
});"""


# ──────────────────────────────────────────────────────────────────
# 格式化工具函数
# ──────────────────────────────────────────────────────────────────

def _fmt_num(val, decimals: int = 2) -> str:
    """格式化数字，None 显示 —"""
    if val is None:
        return '—'
    return f"{val:.{decimals}f}"

def _fmt_pct(val) -> str:
    """格式化涨跌幅，如 +5.23%"""
    if val is None:
        return '—'
    sign = '+' if val > 0 else ''
    return f"{sign}{val:.2f}%"

def _fmt_vol(val) -> str:
    """格式化成交量（手）"""
    if val is None:
        return '—'
    if val >= 1e8:
        return f"{val/1e8:.2f}亿手"
    if val >= 1e4:
        return f"{val/1e4:.2f}万手"
    return f"{val:.0f}手"

def _fmt_amount(val) -> str:
    """格式化成交额（元 → 亿元）"""
    if val is None:
        return '—'
    return f"{val/1e8:.2f}亿"

def _fmt_yi(val) -> str:
    """格式化亿元（已经是亿元单位）"""
    if val is None:
        return '—'
    return f"{val:.2f}亿"

def _fmt_wan(val) -> str:
    """格式化万元（已经是万元单位）"""
    if val is None:
        return '—'
    return f"{val:.2f}"

def _fmt_ratio(val) -> str:
    """格式化量能比"""
    if val is None:
        return '—'
    return f"{val:.2f}x"

def _pct_class(val) -> str:
    """根据涨跌幅返回 CSS 类名"""
    if val is None:
        return 'flat'
    if val > 0:
        return 'up'
    if val < 0:
        return 'down'
    return 'flat'
