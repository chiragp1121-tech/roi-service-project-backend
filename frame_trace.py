"""
Formula tracing for the Frame Services Calculator.

Renders the result tables as one HTML view. Hover over any calculated cell to:
  * see the formula (with the actual numbers) in a tooltip, and
  * see every cell that feeds that calculation highlighted - including cells
    in other tables (e.g. the margin table pulls from the Total rows of the
    Current / Future tables and from the Cost and Schedule table) and the
    X / Y / Z values from the Premises.

The formulas here only DESCRIBE the logic in
roi_calculator.py; they do not compute
anything. If a formula changes in the calculator, update the matching note.
"""

import html
import numbers

import pandas as pd

import roi_calculator as calc


TALENT = {
    "side": "talent",
    "name": "Talent",
    "num": "Number of Services (Talent)",
    "fte": "% FTE/Service (Talent)",
    "tot": "Talent Total % FTE",
    "cost": "Talent Service Cost (K$)",
    "val": "Talent Service Value (K$)",
    "yr": "Talent Yearly Margin Contribution (K$)",
    "mo": "Talent Monthly Margin Contribution (K$)",
    "base": "fte",  # Talent value is based on total % FTE
}
AI = {
    "side": "ai",
    "name": "AI",
    "num": "Number of Services (AI)",
    "fte": "% FTE/Service (AI)",
    "tot": "AI Total % FTE",
    "cost": "AI Service Cost (K$)",
    "val": "AI Service Value (K$)",
    "yr": "AI Yearly Margin Contribution (K$)",
    "mo": "AI Monthly Margin Contribution (K$)",
    "base": "fte",  # AI value is based on total % FTE
}
COMB = {
    "cost": "Talent+AI Total % FTE Cost",
    "val": "Talent+AI Service Value",
    "yr": "Talent+AI Yearly Margin Contribution (K$)",
    "mo": "Talent+AI Monthly Margin Contribution (K$)",
}


# =========================================================
# HELPERS
# =========================================================

def _isnum(v):
    if v is None or isinstance(v, (bool, str)):
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        return False
    return isinstance(v, numbers.Number)


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, numbers.Number):
        s = f"{float(v):,.2f}".rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    return str(v)


class Grid:
    """One table + a note (formula text and dependency ids) per cell."""

    def __init__(self, key, title, df):
        self.key = key
        self.title = title
        self.df = df
        self.notes = {}  # (row, col) -> (tooltip text, [dep ids])

    def cid(self, r, col):
        return f"{self.key}-{r}-{list(self.df.columns).index(col)}"

    def v(self, r, col):
        return self.df.iloc[r][col]

    def f(self, r, col):
        return fmt(self.v(r, col))

    def note(self, r, col, formula, numbers_, deps):
        result = self.f(r, col)
        text = f"{col}\n{formula}\n= {numbers_}"
        if result != numbers_:
            text += f" = {result}"
        self.notes[(r, col)] = (text, [d for d in deps if d])

    def info(self, r, col, message):
        self.notes[(r, col)] = (f"{col}\n{message}", [])


def _total_ref(grid, col):
    """(cell id, display value) of a column's Total row, or (None, '0')."""
    if grid.df.empty or col not in grid.df.columns:
        return None, "0"
    n = len(grid.df) - 1
    return grid.cid(n, col), grid.f(n, col) or "0"


# =========================================================
# PREMISES
# =========================================================

def build_premises_grid(premises):
    """Display tier assumptions in X/Y/Z columns while keeping each tier traceable."""
    rows = []
    keys_by_row = []
    for period in ("current", "future"):
        for side, name in (("talent", "Talent"), ("ai", "AI")):
            for metric in ("cost", "value"):
                rate_map = premises[period][side][metric]
                rows.append({
                    "Premises": f"{period.title()} {name} FTE {metric.title()} (K$ per FTE)",
                    "X": rate_map["X"],
                    "Y": rate_map["Y"],
                    "Z": rate_map["Z"],
                })
                keys_by_row.append((period, side, metric))
    g = Grid("pre", "Premises Assumptions", pd.DataFrame(rows))
    ids = {}
    for r, (period, side, metric) in enumerate(keys_by_row):
        for tier in ("X", "Y", "Z"):
            ids[(period, side, metric, tier)] = g.cid(r, tier)
            g.notes[(r, tier)] = (
                f"{period.title()} {side.title()} FTE {metric.title()} — tier {tier}\n"
                "Input from the Premises tab.",
                [],
            )
    return g, ids


# =========================================================
# CURRENT / FUTURE SERVICES
# =========================================================

def build_service_grid(key, title, df, period, premises, pre):
    g = Grid(key, title, df)
    if df.empty:
        return g
    n = len(df) - 1
    for r in range(n):
        for s in (TALENT, AI):
            name, side = s["name"], s["side"]
            num, fte = s["num"], s["fte"]
            tot, cost, val, yr, mo = s["tot"], s["cost"], s["val"], s["yr"], s["mo"]
            for col in (num, fte):
                if col in df.columns:
                    g.info(r, col, "Input from the Excel file.")
            g.note(r, tot, f"{num} × {fte}", f"{g.f(r, num)} × {g.f(r, fte)}", [g.cid(r, num), g.cid(r, fte)])
            tier_col = "Talent Tier" if side == "talent" else "AI Tier"
            tier = str(df.iloc[r].get(tier_col, "X")).strip().upper()
            if tier not in ("X", "Y", "Z"):
                tier = "X"
            cost_rate = premises[period][side]["cost"][tier]
            value_rate = premises[period][side]["value"][tier]
            cost_id = pre[(period, side, "cost", tier)]
            value_id = pre[(period, side, "value", tier)]
            tier_dep = [g.cid(r, tier_col)] if tier_col in df.columns else []
            g.note(r, cost, f"{tot} × {period.title()} {name} FTE Cost (tier {tier}) ÷ 100", f"{g.f(r, tot)} × {fmt(cost_rate)} ÷ 100", [g.cid(r, tot), cost_id] + tier_dep)
            if s["base"] == "cost":
                g.note(r, val, f"{cost} × {period.title()} {name} FTE Value (tier {tier}) ÷ 100", f"{g.f(r, cost)} × {fmt(value_rate)} ÷ 100", [g.cid(r, cost), value_id] + tier_dep)
            else:
                g.note(r, val, f"{tot} × {period.title()} {name} FTE Value (tier {tier}) ÷ 100", f"{g.f(r, tot)} × {fmt(value_rate)} ÷ 100", [g.cid(r, tot), value_id] + tier_dep)
            g.note(r, yr, f"{val} − {cost}", f"{g.f(r, val)} − {g.f(r, cost)}", [g.cid(r, val), g.cid(r, cost)])
            g.note(r, mo, f"{yr} ÷ 12", f"{g.f(r, yr)} ÷ 12", [g.cid(r, yr)])
        for col, formula, a, b in (
            (COMB["cost"], f"{TALENT['cost']} + {AI['cost']}", TALENT["cost"], AI["cost"]),
            (COMB["val"], f"{TALENT['val']} + {AI['val']}", TALENT["val"], AI["val"]),
            (COMB["yr"], f"{TALENT['yr']} + {AI['yr']}", TALENT["yr"], AI["yr"]),
            (COMB["mo"], f"{TALENT['mo']} + {AI['mo']}", TALENT["mo"], AI["mo"]),
        ):
            if col in df.columns:
                g.note(r, col, formula, f"{g.f(r, a)} + {g.f(r, b)}", [g.cid(r, a), g.cid(r, b)])
    for col in df.columns:
        if _isnum(g.v(n, col)) and n > 0:
            g.note(n, col, f"Sum of '{col}' for all service rows above", " + ".join(g.f(r, col) for r in range(n)), [g.cid(r, col) for r in range(n)])
    return g


# =========================================================
# COST AND SCHEDULE TO REACH FUTURE SERVICES
# =========================================================

def build_schedule_grid(df, premises, pre):
    g = Grid("sch", "Cost and Schedule to reach Future services", df)
    if df.empty:
        return g

    sides = [
        ("talent", "Talent", "Talent Total % FTE per service",
         "Talent Total Service Cost* (K$)",
         "Talent Monthly Margin Contribution (K$)", "cost"),
        ("ai", "AI", "AI Total % FTE per service",
         "AI Total Service Cost** (K$)",
         "AI Monthly Margin Contribution (K$)", "fte"),
    ]

    for side, name, fte, cost, mo, base in sides:
        x_cost_rates = premises["current"][side]["cost"]
        x_value_rates = premises["current"][side]["value"]
        x_cost = sum(float(v) for v in x_cost_rates.values()) / 3
        x_value = sum(float(v) for v in x_value_rates.values()) / 3
        x_cost_ids = [pre[("current", side, "cost", tier)] for tier in ("X", "Y", "Z")]
        x_value_ids = [pre[("current", side, "value", tier)] for tier in ("X", "Y", "Z")]

        for r in range(len(df)):
            if r == 2:
                g.note(
                    r, fte,
                    f"{fte} (row 1) + {fte} (row 2)",
                    f"{g.f(0, fte)} + {g.f(1, fte)}",
                    [g.cid(0, fte), g.cid(1, fte)],
                )
            else:
                g.info(r, fte, "Entered by you at the top of the page.")

            g.note(
                r, cost,
                f"{fte} × Current {name} FTE Cost",
                f"{g.f(r, fte)} × {fmt(x_cost)}",
                [g.cid(r, fte)] + x_cost_ids,
            )

        if len(df) > 3 and _isnum(g.v(3, mo)):
            g.note(
                3, mo,
                f"{cost} (recurring row) ÷ 12",
                f"{g.f(3, cost)} ÷ 12",
                [g.cid(3, cost)],
            )

    both = "Talent+AI Monthly Margin Contribution (K$)"
    if len(df) > 3 and _isnum(g.v(3, both)):
        t_mo = "Talent Monthly Margin Contribution (K$)"
        a_mo = "AI Monthly Margin Contribution (K$)"
        g.note(
            3, both,
            f"{t_mo} + {a_mo}",
            f"{g.f(3, t_mo)} + {g.f(3, a_mo)}",
            [g.cid(3, t_mo), g.cid(3, a_mo)],
        )
    return g


# =========================================================
# FUTURE-CURRENT SERVICE MARGIN CONTRIBUTION
# =========================================================

def build_margin_grid(df, cur, fut, sch):
    g = Grid("mar", "Future-Current Service Margin Contribution", df)
    if df.empty:
        return g

    TY = "Talent Yearly Margin Contribution (K$)"
    TM = "Talent Monthly Margin Contribution (K$)"
    AY = "AI Yearly Margin Contribution (K$)"
    AM = "AI Monthly Margin Contribution (K$)"
    BY = "Talent+AI Yearly Margin Contribution (K$)"
    BM = "Talent+AI Monthly Margin Contribution (K$)"

    def has(r, c):
        return _isnum(g.v(r, c))

    ROW1 = "Net Gain or Loss (row 1)"
    ROW2 = "NRE cost (row 2)"
    ROW3 = "Net Margin Year 1 (row 3)"

    # ---- Row 1: Future total - Current total ----
    for col in (TY, TM, AY, AM):
        if has(0, col):
            f_id, f_val = _total_ref(fut, col)
            c_id, c_val = _total_ref(cur, col)
            g.note(
                0, col,
                f"Future Total − Current Total of '{col}'",
                f"{f_val} − {c_val}",
                [f_id, c_id],
            )
    for col, t_col, a_col in ((BY, TY, AY), (BM, TM, AM)):
        if has(0, col):
            ft, ft_v = _total_ref(fut, t_col)
            fa, fa_v = _total_ref(fut, a_col)
            ct, ct_v = _total_ref(cur, t_col)
            ca, ca_v = _total_ref(cur, a_col)
            g.note(
                0, col,
                f"(Future Talent + Future AI) − (Current Talent + Current AI), "
                f"using the Total rows of '{t_col}' and '{a_col}'",
                f"({ft_v} + {fa_v}) − ({ct_v} + {ca_v})",
                [ft, fa, ct, ca],
            )

    # ---- Row 2: NRE cost from the Cost and Schedule table ----
    sch_cols = {
        TY: ("Talent Total Service Cost* (K$)", 2, "Total Investment (schedule row 3)"),
        TM: ("Talent Total Service Cost* (K$)", 3, "Recurring Cost (schedule row 4)"),
        AY: ("AI Total Service Cost** (K$)", 2, "Total Investment (schedule row 3)"),
        AM: ("AI Total Service Cost** (K$)", 3, "Recurring Cost (schedule row 4)"),
    }
    for col, (s_col, s_row, label) in sch_cols.items():
        if has(1, col) and len(sch.df) > s_row:
            g.note(
                1, col,
                f"{s_col} – {label} ÷ 100",
                f"{sch.f(s_row, s_col)} ÷ 100",
                [sch.cid(s_row, s_col)],
            )
    for col, t_col, a_col in ((BY, TY, AY), (BM, TM, AM)):
        if has(1, col):
            g.note(
                1, col,
                f"Talent {ROW2} + AI {ROW2}",
                f"{g.f(1, t_col)} + {g.f(1, a_col)}",
                [g.cid(1, t_col), g.cid(1, a_col)],
            )

    # ---- Row 3: Net Margin Year 1 ----
    for col, m_col in ((TY, TM), (AY, AM)):
        if has(2, col):
            who = "Talent" if col == TY else "AI"
            g.note(
                2, col,
                f"{who} {ROW1} − {who} recurring NRE (row 2, monthly) "
                f"− {who} investment NRE (row 2, yearly) ÷ 12",
                f"{g.f(0, col)} − {g.f(1, m_col)} − {g.f(1, col)} ÷ 12",
                [g.cid(0, col), g.cid(1, m_col), g.cid(1, col)],
            )
    if has(2, BY):
        g.note(
            2, BY,
            f"Talent {ROW3} + AI {ROW3}",
            f"{g.f(2, TY)} + {g.f(2, AY)}",
            [g.cid(2, TY), g.cid(2, AY)],
        )

    # ---- Row 4: ROI ----
    if has(3, TY):
        g.note(
            3, TY,
            f"Talent {ROW3} ÷ Talent {ROW2} × 100",
            f"{g.f(2, TY)} ÷ {g.f(1, TY)} × 100",
            [g.cid(2, TY), g.cid(1, TY)],
        )
    if has(3, AY):
        g.note(
            3, AY,
            f"AI {ROW1} ÷ AI {ROW2} × 100",
            f"{g.f(0, AY)} ÷ {g.f(1, AY)} × 100",
            [g.cid(0, AY), g.cid(1, AY)],
        )
    if has(3, BY):
        g.note(
            3, BY,
            f"Talent+AI {ROW1} ÷ Talent+AI {ROW2} × 100",
            f"{g.f(0, BY)} ÷ {g.f(1, BY)} × 100",
            [g.cid(0, BY), g.cid(1, BY)],
        )

    # ---- Row 5: Months to breakeven ----
    for y_col, m_col in ((TY, TM), (AY, AM), (BY, BM)):
        if has(4, m_col):
            who = {TY: "Talent", AY: "AI", BY: "Talent+AI"}[y_col]
            g.note(
                4, m_col,
                f"{who} {ROW2} (yearly) ÷ ({who} {ROW1} monthly − "
                f"{who} {ROW2} monthly)",
                f"{g.f(1, y_col)} ÷ ({g.f(0, m_col)} − {g.f(1, m_col)})",
                [g.cid(1, y_col), g.cid(0, m_col), g.cid(1, m_col)],
            )
    return g


# =========================================================
# HTML
# =========================================================

CSS = """
body{margin:0;padding:0 4px 20px;display:flow-root;background:#fff;color:#1f2430;
  font-family:"Source Sans Pro",-apple-system,Segoe UI,Roboto,sans-serif;font-size:13px}
h3{font-size:18px;margin:22px 0 6px;font-weight:600}
.legend{font-size:12px;color:#555;margin:6px 0 2px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.legend span.sw{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-3px;margin-right:4px}
.wrap{overflow-x:auto;border:1px solid #e3e5ea;border-radius:6px}
table{border-collapse:collapse;width:100%}
th{background:#f3f4f7;font-weight:600;text-align:left;white-space:nowrap;
  padding:6px 10px;border-bottom:1px solid #dcdfe6;position:sticky;top:0}
td{padding:5px 10px;border-bottom:1px solid #eef0f4;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.tot td{font-weight:700;background:#fafbfc}
td.c{cursor:help}
td.c:hover,td.hl-self{outline:2px solid #f08c00;outline-offset:-2px;background:#fff4e0}
td.hl-dep{background:#fff3a3 !important;outline:2px solid #e0b400;outline-offset:-2px}
#tip{position:fixed;display:none;z-index:99;max-width:460px;background:#1f2430;color:#fff;
  padding:8px 11px;border-radius:6px;font-size:12px;line-height:1.45;white-space:pre-wrap;
  box-shadow:0 4px 14px rgba(0,0,0,.28);pointer-events:none}
.empty{color:#8a6d00;background:#fff8e1;padding:8px 12px;border-radius:6px}
"""

JS = """
const tip = document.getElementById('tip');
function clearHl(){
  document.querySelectorAll('.hl-self,.hl-dep').forEach(e => e.classList.remove('hl-self','hl-dep'));
}
function place(ev){
  const pad = 14;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  if (x + w > window.innerWidth - 4) x = Math.max(4, ev.clientX - w - pad);
  if (y + h > window.innerHeight - 4) y = Math.max(4, ev.clientY - h - pad);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
document.addEventListener('mouseover', function(ev){
  const td = ev.target.closest('td[data-f]');
  clearHl();
  if (!td){ tip.style.display = 'none'; return; }
  td.classList.add('hl-self');
  (td.dataset.d || '').split(' ').filter(Boolean).forEach(function(id){
    const el = document.getElementById(id);
    if (el) el.classList.add('hl-dep');
  });
  tip.textContent = td.dataset.f;
  tip.style.display = 'block';
  place(ev);
});
document.addEventListener('mousemove', function(ev){
  if (tip.style.display === 'block') place(ev);
});
document.addEventListener('mouseleave', function(){ clearHl(); tip.style.display = 'none'; });

// Resize the host iframe to exactly fit the content (no empty space below).
function fit(){
  try {
    const h = document.body.offsetHeight + 4;
    const fe = window.frameElement;
    if (fe) { fe.style.height = h + 'px'; fe.setAttribute('height', h); }
  } catch (e) { /* cross-origin: keep the fallback height */ }
}
window.addEventListener('load', fit);
window.addEventListener('resize', fit);
if (window.ResizeObserver) new ResizeObserver(fit).observe(document.body);
fit();
"""


def _grid_html(g, empty_message):
    out = [f"<h3>{html.escape(g.title)}</h3>"]
    if g.df.empty:
        out.append(f'<div class="empty">{html.escape(empty_message)}</div>')
        return "".join(out)

    df = g.df
    out.append('<div class="wrap"><table><thead><tr>')
    for col in df.columns:
        numeric_col = any(_isnum(v) for v in df[col])
        th_cls = ' class="n"' if numeric_col else ""
        out.append(f"<th{th_cls}>{html.escape(str(col))}</th>")
    out.append("</tr></thead><tbody>")

    last = len(df) - 1
    for r in range(len(df)):
        is_total = (
            g.key in ("cur", "fut")
            and str(df.iloc[r].get("Service Improvement", "")).strip().lower()
            == "total"
        )
        out.append('<tr class="tot">' if is_total else "<tr>")
        for j, col in enumerate(df.columns):
            value = df.iloc[r][col]
            classes = []
            if _isnum(value):
                classes.append("n")
            attrs = f' id="{g.key}-{r}-{j}"'
            note = g.notes.get((r, col))
            if note and fmt(value) != "":
                text, deps = note
                classes.append("c")
                attrs += f' data-f="{html.escape(text, quote=True)}"'
                if deps:
                    attrs += f' data-d="{html.escape(" ".join(deps), quote=True)}"'
            cls = f' class="{" ".join(classes)}"' if classes else ""
            out.append(f"<td{cls}{attrs}>{html.escape(fmt(value))}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def build_traced_html(current_df, future_df, schedule_df, margin_df, premises, show_legend=True):
    """Return (html_string, suggested_height_px)."""
    pre_grid, pre_ids = build_premises_grid(premises)
    cur = build_service_grid("cur", "Current Services", current_df, "current", premises, pre_ids)
    fut = build_service_grid("fut", "Future Services", future_df, "future", premises, pre_ids)
    sch = build_schedule_grid(schedule_df, premises, pre_ids)
    mar = build_margin_grid(margin_df, cur, fut, sch)

    parts = [
        ('<div class="legend"><b>Hover over a calculated cell</b> to see its formula. '
        '<span><span class="sw" style="background:#fff4e0;border:2px solid #f08c00"></span>selected formula</span>'
        '<span><span class="sw" style="background:#fff3a3;border:2px solid #e0b400"></span>cells used in calculation</span>'
        "</div>" if show_legend else ""),
        _grid_html(cur, "No Current Services rows were found."),
        _grid_html(fut, "No Future Services rows were found."),
        _grid_html(sch, "No schedule data."),
        _grid_html(mar, "No margin data."),
        _grid_html(pre_grid, "No premises data."),
    ]

    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>"
        + "".join(parts)
        + f"<div id='tip'></div><script>{JS}</script></body></html>"
    )

    rows = sum(len(g.df) + 1 for g in (cur, fut, sch, mar, pre_grid))
    height = 40 + 5 * 55 + rows * 30
    return doc, height


def render_traced_tables(current_df, future_df, schedule_df, margin_df, premises, show_legend=True):
    """Show all result tables with hover-formula + dependency highlighting."""
    import streamlit.components.v1 as components

    doc, height = build_traced_html(
        current_df, future_df, schedule_df, margin_df, premises, show_legend=show_legend
    )
    components.html(doc, height=height, scrolling=True)

def render_formula_table(df, title, formula_builder, show_legend=True):
    """Render a table with formula tooltips and same-row dependency highlighting."""
    import streamlit.components.v1 as components
    import html as _html
    import pandas as _pd

    if df is None or df.empty:
        return

    columns = list(df.columns)
    col_indexes = {str(col): idx for idx, col in enumerate(columns)}
    headers = "".join(f"<th>{_html.escape(str(c))}</th>" for c in columns)
    body = []
    for r_idx, (_, row) in enumerate(df.iterrows()):
        cells = []
        for col_idx, col in enumerate(columns):
            value = row[col]
            info = formula_builder(r_idx, row, col, value)
            formula, dependencies = (info if isinstance(info, tuple) else (info, []))
            attr = f' id="cell-{r_idx}-{col_idx}"'
            classes = []
            if formula:
                attr += f' title="{_html.escape(str(formula), quote=True)}"'
                classes.append("formula-cell")
            dep_indexes = [
                str(col_indexes[str(dep)])
                for dep in (dependencies or [])
                if str(dep) in col_indexes and str(dep) != str(col)
            ]
            if dep_indexes:
                attr += f' data-deps="{",".join(dep_indexes)}"'
            if classes:
                attr += f' class="{" ".join(classes)}"'
            display = "" if value is None or (not isinstance(value, str) and _pd.isna(value)) else str(value)
            if isinstance(value, float):
                display = f"{value:,.2f}".rstrip("0").rstrip(".")
            cells.append(f"<td{attr}>{_html.escape(display)}</td>")
        body.append(f'<tr data-row="{r_idx}">' + "".join(cells) + "</tr>")

    legend_html = """<div class="legend"><b>Hover over a calculated cell</b> to see its formula.
      <span><span class="sw" style="background:#fff0d6;border:2px solid #f08c00"></span>selected formula</span>
      <span><span class="sw" style="background:#fff3a3;border:1px solid #e0b400"></span>cells used in calculation</span>
    </div>""" if show_legend else ""
    doc = f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
    body{{font-family:Arial,sans-serif;font-size:12px;color:#233044}}
    .wrap{{overflow:auto;max-width:100%;border:1px solid #ddd;border-radius:6px}}
    table{{border-collapse:collapse;width:max-content;min-width:100%;white-space:nowrap}}
    th,td{{border:1px solid #e5e7eb;padding:7px 9px;text-align:left}}
    th{{background:#f5f6f8;font-weight:600;position:sticky;top:0}}
    td.formula-cell{{cursor:help}}
    td.formula-cell:hover,.formula-active{{background:#fff0d6!important;outline:2px solid #f08c00;outline-offset:-2px}}
    td.dependency-cell{{background:#fff3a3!important;outline:1px solid #e0b400;outline-offset:-1px}}
    .legend{{display:flex;gap:12px;align-items:center;margin:7px 0 9px;font-size:11px;flex-wrap:wrap}}
    .sw{{display:inline-block;width:11px;height:11px;margin-right:4px;border:1px solid #999;vertical-align:middle}}
    </style></head><body>
    <div class="legend"><b>Hover over a calculated cell</b> to see its formula.
      <span><span class="sw" style="background:#fff0d6;border:2px solid #f08c00"></span>selected formula</span>
      <span><span class="sw" style="background:#fff3a3;border:1px solid #e0b400"></span>cells used in calculation</span>
    </div>
    <div class="wrap"><table><thead><tr>{headers}</tr></thead>
    <tbody>{''.join(body)}</tbody></table></div>
    <script>
    const cells = document.querySelectorAll('td[data-deps]');
    function clearTrace() {{
      document.querySelectorAll('.formula-active,.dependency-cell').forEach(el => {{
        el.classList.remove('formula-active','dependency-cell');
      }});
    }}
    document.querySelectorAll('td.formula-cell').forEach(cell => {{
      cell.addEventListener('mouseenter', () => {{
        clearTrace();
        cell.classList.add('formula-active');
        const row = cell.parentElement;
        const indexes = (cell.dataset.deps || '').split(',').filter(Boolean);
        indexes.forEach(index => {{
          const dep = row.children[Number(index)];
          if (dep) dep.classList.add('dependency-cell');
        }});
      }});
      cell.addEventListener('mouseleave', clearTrace);
    }});
    </script></body></html>
    """
    height = min(700, max(190, 85 + (len(df) + 1) * 34))
    components.html(doc, height=height, scrolling=True)
