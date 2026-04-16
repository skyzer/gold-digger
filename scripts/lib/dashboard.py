"""Static HTML dashboard — single file, no server, no JavaScript framework.

Generates a self-contained HTML file that opens in any browser. Reads the
latest export.json and renders:
  - Project cards with price, mcap, change %, mentions
  - KOL digest summary
  - Narrative rotation chart (CSS bars)
  - Action queue
  - Brief report

No build step, no npm, no framework. One HTML file with embedded CSS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from lib import storage, export as export_lib


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        color = "#22c55e" if f >= 0 else "#ef4444"
        return f'<span style="color:{color}">{f:+.1f}%</span>'
    except (TypeError, ValueError):
        return str(v)


def _mcap(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if f >= 1e9:
            return f"${f/1e9:.2f}B"
        if f >= 1e6:
            return f"${f/1e6:.1f}M"
        if f >= 1e3:
            return f"${f/1e3:.0f}k"
        return f"${f:.0f}"
    except (TypeError, ValueError):
        return str(v)


def _project_card(p: Dict[str, Any]) -> str:
    tier = p.get("tier", "tracked")
    tier_color = {"tracked": "#3b82f6", "scout": "#f59e0b", "archived": "#6b7280"}.get(tier, "#6b7280")
    narratives = ", ".join(p.get("narrative") or ["—"])
    mentions = (p.get("mention_count_7d") or 0) + (p.get("mention_count_30d") or 0)
    return f"""
    <div class="card">
      <div class="card-header">
        <h3>{p.get('name', p.get('slug', '?'))}</h3>
        <span class="badge" style="background:{tier_color}">{tier}</span>
      </div>
      <div class="card-ticker">{p.get('ticker') or '—'}</div>
      <div class="card-grid">
        <div class="metric">
          <div class="metric-label">Price</div>
          <div class="metric-value">${p.get('price_usd') or '—'}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Mcap</div>
          <div class="metric-value">{_mcap(p.get('mcap'))}</div>
        </div>
        <div class="metric">
          <div class="metric-label">24h</div>
          <div class="metric-value">{_pct(p.get('change_24h_pct'))}</div>
        </div>
        <div class="metric">
          <div class="metric-label">7d</div>
          <div class="metric-value">{_pct(p.get('change_7d_pct'))}</div>
        </div>
        <div class="metric">
          <div class="metric-label">30d</div>
          <div class="metric-value">{_pct(p.get('change_30d_pct'))}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Mentions</div>
          <div class="metric-value">{mentions}</div>
        </div>
      </div>
      <div class="card-narratives">{narratives}</div>
      <div class="card-meta">
        {f'GH: {p.get("github_stars")}★' if p.get("github_stars") else ''}
        {f' · {len(p.get("exchanges") or [])} exchanges' if p.get("exchanges") else ''}
        {f' · KOLs: {", ".join(p.get("mentioned_by") or [])}' if p.get("mentioned_by") else ''}
      </div>
    </div>"""


def build_dashboard() -> str:
    """Generate the full HTML string."""
    data = export_lib.build_export()
    projects = data.get("projects", [])
    summary = data.get("summary", {})
    kol_memory = data.get("kol_memory", [])
    reports = data.get("recent_reports", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Sort projects: tracked first, then by mcap desc
    tracked = [p for p in projects if p.get("tier") == "tracked"]
    scouts = [p for p in projects if p.get("tier") == "scout"]
    tracked.sort(key=lambda p: (p.get("mcap") or 0), reverse=True)
    scouts.sort(key=lambda p: (p.get("mcap") or 0), reverse=True)

    project_cards = "\n".join(_project_card(p) for p in tracked + scouts)

    # KOL memory table
    kol_rows = ""
    for m in kol_memory[:20]:
        kol_rows += f"""<tr>
          <td>{m.get('first_seen', '')}</td>
          <td>@{m.get('kol', '')}</td>
          <td>${m.get('ticker', '')}</td>
          <td>{m.get('resolved_slug') or '—'}</td>
          <td><span class="badge-sm">{m.get('action', '')}</span></td>
        </tr>"""

    # Latest brief
    latest_brief = ""
    if reports:
        latest_brief = reports[-1].get("brief", "").replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gold Digger Dashboard</title>
<style>
  :root {{
    --bg: #0a0a0a; --surface: #141414; --border: #262626;
    --text: #e5e5e5; --text-dim: #737373; --accent: #f59e0b;
    --green: #22c55e; --red: #ef4444; --blue: #3b82f6;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); padding: 24px;
    max-width: 1400px; margin: 0 auto;
  }}
  h1 {{ font-size: 28px; margin-bottom: 4px; }}
  h2 {{ font-size: 20px; margin: 32px 0 16px; color: var(--accent); }}
  .subtitle {{ color: var(--text-dim); font-size: 14px; margin-bottom: 24px; }}
  .stats {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }}
  .stat {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: 8px; padding: 16px 20px; min-width: 140px; }}
  .stat-value {{ font-size: 24px; font-weight: 700; }}
  .stat-label {{ font-size: 12px; color: var(--text-dim); margin-top: 4px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px; transition: border-color 0.2s;
  }}
  .card:hover {{ border-color: var(--accent); }}
  .card-header {{ display: flex; justify-content: space-between; align-items: center; }}
  .card-header h3 {{ font-size: 18px; }}
  .badge {{
    font-size: 11px; padding: 2px 8px; border-radius: 4px;
    color: #fff; font-weight: 600; text-transform: uppercase;
  }}
  .badge-sm {{
    font-size: 10px; padding: 1px 6px; border-radius: 3px;
    background: var(--border); color: var(--text-dim);
  }}
  .card-ticker {{ font-size: 14px; color: var(--text-dim); margin: 4px 0 12px; }}
  .card-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
  .metric {{ text-align: center; }}
  .metric-label {{ font-size: 11px; color: var(--text-dim); }}
  .metric-value {{ font-size: 16px; font-weight: 600; }}
  .card-narratives {{
    font-size: 12px; color: var(--accent); margin-top: 12px;
    padding-top: 8px; border-top: 1px solid var(--border);
  }}
  .card-meta {{ font-size: 11px; color: var(--text-dim); margin-top: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-dim); font-size: 12px; text-transform: uppercase; }}
  .brief {{ background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; padding: 20px; font-size: 14px; line-height: 1.8; }}
  .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border);
             font-size: 12px; color: var(--text-dim); text-align: center; }}
</style>
</head>
<body>
  <h1>Gold Digger</h1>
  <p class="subtitle">Compounding crypto-AI research · Generated {now}</p>

  <div class="stats">
    <div class="stat">
      <div class="stat-value">{summary.get('total_projects', 0)}</div>
      <div class="stat-label">Projects</div>
    </div>
    <div class="stat">
      <div class="stat-value">{summary.get('tracked', 0)}</div>
      <div class="stat-label">Tracked</div>
    </div>
    <div class="stat">
      <div class="stat-value">{summary.get('scout', 0)}</div>
      <div class="stat-label">Scout</div>
    </div>
    <div class="stat">
      <div class="stat-value">{summary.get('total_kols', 0)}</div>
      <div class="stat-label">KOLs</div>
    </div>
    <div class="stat">
      <div class="stat-value">{summary.get('kol_mentions_recorded', 0)}</div>
      <div class="stat-label">KOL Calls</div>
    </div>
    <div class="stat">
      <div class="stat-value">{summary.get('daily_reports', 0)}</div>
      <div class="stat-label">Daily Reports</div>
    </div>
  </div>

  <h2>Latest Brief</h2>
  <div class="brief">{latest_brief or '<em>No reports yet. Run gold-digger daily.</em>'}</div>

  <h2>Projects</h2>
  <div class="cards">{project_cards}</div>

  <h2>KOL Memory</h2>
  <table>
    <thead><tr><th>Date</th><th>KOL</th><th>Ticker</th><th>Resolved</th><th>Action</th></tr></thead>
    <tbody>{kol_rows or '<tr><td colspan="5"><em>No KOL mentions recorded yet.</em></td></tr>'}</tbody>
  </table>

  <div class="footer">
    Gold Digger v0.5 · Research compounds over time · Data: {data.get('data_root', '')}
  </div>
</body>
</html>"""


def write_dashboard() -> Path:
    """Write dashboard.html to the data root."""
    root = storage.data_root()
    html = build_dashboard()
    path = root / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path
