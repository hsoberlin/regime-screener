"""
build_dashboard.py
Render screener_output.json jadi dashboard.html mandiri (data ditanam langsung,
tanpa koneksi eksternal) -- sama filosofinya dengan Setup Board.
"""
import json

with open("screener_output.json") as f:
    DATA = json.load(f)

FASE_LABEL = {
    "BEAR (belum rebound 20%)": ("BEAR", "danger"),
    "BOTTOM-REBOUND (terkonfirmasi)": ("BOTTOM-REBOUND", "warning"),
    "NORMALIZING": ("NORMALIZING", "success"),
    "NORMAL (tidak dalam bear market >=20%)": ("NORMAL", "neutral"),
}

TIER_LABEL = {
    "kandidat_kuat": ("Kandidat kuat", "success"),
    "menunggu_konfirmasi": ("Menunggu konfirmasi", "warning"),
    "gap_tidak_signifikan": ("Gap tidak signifikan", "neutral"),
}

def traffic_light(fase, backtest):
    if fase.startswith("BOTTOM-REBOUND"):
        return "hijau", "Fase rebound awal -- syarat sektor & saham aktif dicari"
    if fase == "NORMALIZING":
        b40 = next((b for b in backtest if b["horizon_hari"] == 40), None)
        if b40 and b40["pct_positif"] >= 70:
            return "kuning", "Sudah lewat fase awal (>20% dari bottom) -- masih ada peluang tapi tidak seoptimal fase rebound awal"
        return "kuning", "Fase transisi -- perlu lebih selektif"
    if fase.startswith("BEAR"):
        return "merah", "Masih tren turun, belum ada konfirmasi rebound -- strategi laggard-hunting belum relevan"
    return "merah", "Tidak ada bear market aktif -- strategi ini dirancang khusus untuk fase bottom-rebound"

light, light_note = traffic_light(DATA["ihsg"]["fase"], DATA["backtest_summary"])
fase_label, fase_color = FASE_LABEL.get(DATA["ihsg"]["fase"], (DATA["ihsg"]["fase"], "neutral"))

def render_sector_cards():
    html = ""
    for s in DATA["sektor"]:
        status = "Sudah bergerak" if s["sudah_bergerak"] else "Belum bergerak"
        status_class = "badge-success" if s["sudah_bergerak"] else "badge-neutral"
        html += f"""
        <div class="card sector-card">
          <div class="row-between">
            <span class="ticker">#{s['ranking']} {s['sektor']}</span>
            <span class="badge {status_class}">{status}</span>
          </div>
          <p class="muted">Return sejak bottom: <strong>{s['return_sejak_bottom_pct']:+.1f}%</strong> ({s['n_saham']} saham)</p>
        </div>"""
    return html

def sparkline(prices, volumes):
    if not prices or len(prices) < 2:
        return ""
    lo, hi = min(prices), max(prices)
    rng = (hi - lo) or 1
    w, h = 340, 60
    pts = []
    for i, p in enumerate(prices):
        x = i / (len(prices) - 1) * w
        y = h - ((p - lo) / rng * h)
        pts.append(f"{x:.1f},{y:.1f}")
    line = " ".join(pts)

    vmax = max(volumes) or 1
    bars = ""
    for i, v in enumerate(volumes):
        bar_h = max(2, v / vmax * 26)
        color = "#5DCAA5" if i == 0 or prices[i] >= prices[i-1] else "#F0997B"
        if i >= len(volumes) - 2:
            color = "#1D9E75"
        bars += f'<div style="flex:1;background:{color};height:{bar_h:.0f}px;"></div>'

    return f"""
    <svg viewBox="0 0 {w} {h}" style="width:100%;height:60px;display:block;margin-top:8px;">
      <polyline points="{line}" fill="none" stroke="#1D9E75" stroke-width="2"/>
    </svg>
    <div style="display:flex;align-items:flex-end;gap:2px;height:28px;margin-top:4px;">{bars}</div>
    <p class="tiny-muted">Harga 20h &middot; Volume 20h</p>
    """

def render_candidate_cards():
    html = ""
    alokasi_tickers = {a["ticker"] for a in DATA["bobot_ekuitas"].get("alokasi", [])}
    kandidat_menunggu = set(DATA["bobot_ekuitas"].get("kandidat_menunggu", []))

    shown = [c for c in DATA["kandidat"] if c["tier"] in ("kandidat_kuat", "menunggu_konfirmasi")]
    for c in shown:
        label, color = TIER_LABEL.get(c["tier"], (c["tier"], "neutral"))
        badge = f'<span class="badge badge-{color}">{label}</span>'
        exec_badge = ""
        if c["ticker"] in alokasi_tickers:
            badge = '<span class="badge badge-success">All-in Rp20jt</span>'
        elif c["ticker"] in kandidat_menunggu:
            badge = '<span class="badge badge-warning">Cash ditahan</span>'

        penalty_note = ""
        if c["penalty_reasons"]:
            penalty_note = f'<p class="tiny-muted">&#9888; Berat naik: {", ".join(c["penalty_reasons"])}</p>'

        chart = sparkline(c["metrics"]["harga_20h"], c["metrics"]["volume_20h"]) if c["ticker"] in alokasi_tickers else ""

        value_b = c["metrics"]["value_sesi_ini_idr"] / 1e9
        html += f"""
        <div class="card">
          <div class="row-between">
            <span class="ticker">{c['ticker']}</span>
            {badge}
          </div>
          <p class="muted">{c['sektor']} &middot; Gap vs sektor {c['metrics']['gap_vs_sektor_pct']:+.1f}% &middot; Vol {c['metrics']['vol_ratio_today']:.1f}x &middot; Value Rp{value_b:.0f}M</p>
          {penalty_note}
          {chart}
        </div>"""
    return html

def render_equity_card():
    eq = DATA["bobot_ekuitas"]
    status_map = {
        "all_in": ("badge-success", "All-in"),
        "cash_ditahan": ("badge-warning", "Cash ditahan"),
        "cash_menganggur": ("badge-neutral", "Cash menganggur"),
    }
    cls, label = status_map.get(eq["status"], ("badge-neutral", eq["status"]))
    return f"""
    <div class="card">
      <div class="row-between">
        <span class="ticker">Tahap 4 -- Bobot Ekuitas</span>
        <span class="badge {cls}">{label}</span>
      </div>
      <p class="muted">{eq['detail']}</p>
    </div>"""

def render_backtest_table():
    rows = ""
    for b in DATA["backtest_summary"]:
        rows += f"""<tr>
          <td>{b['horizon_hari']}h</td><td>{b['rata_rata_return_%']:+.1f}%</td>
          <td>{b['pct_positif']:.0f}%</td><td>{b['worst_return_%']:+.1f}%</td>
          <td>{b['rata_rata_MAE_%']:+.1f}%</td>
        </tr>"""
    return rows

HTML = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>Regime Screener</title>
<style>
  :root {{
    --bg: #FFFFFF; --surface: #FFFFFF; --border: #E5E3DC;
    --text: #1A1A18; --muted: #6B6A64; --tiny: #9A988F;
    --success-bg: #EAF3DE; --success-text: #27500A; --success-fill:#639922;
    --warning-bg: #FAEEDA; --warning-text: #633806; --warning-fill:#BA7517;
    --danger-bg: #FCEBEB; --danger-text: #791F1F; --danger-fill:#E24B4A;
    --neutral-bg: #F1EFE8; --neutral-text: #444441;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; background: #FAFAF7; color: var(--text); margin:0; padding: 16px; max-width: 720px; margin: 0 auto; }}
  h1 {{ font-size: 18px; font-weight: 500; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; font-weight: 500; margin: 24px 0 10px; }}
  .subtitle {{ font-size: 13px; color: var(--muted); margin: 0 0 20px; }}
  .card {{ background: var(--surface); border: 0.5px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; }}
  .row-between {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }}
  .ticker {{ font-size:14px; font-weight:500; }}
  .muted {{ font-size:12px; color:var(--muted); margin:2px 0; }}
  .tiny-muted {{ font-size:11px; color:var(--tiny); margin:2px 0; }}
  .badge {{ font-size:11px; padding:3px 10px; border-radius:6px; font-weight:500; white-space:nowrap; }}
  .badge-success {{ background:var(--success-bg); color:var(--success-text); }}
  .badge-warning {{ background:var(--warning-bg); color:var(--warning-text); }}
  .badge-danger {{ background:var(--danger-bg); color:var(--danger-text); }}
  .badge-neutral {{ background:var(--neutral-bg); color:var(--neutral-text); }}
  .traffic {{ display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:6px; }}
  .traffic-hijau {{ background:var(--success-fill); }}
  .traffic-kuning {{ background:var(--warning-fill); }}
  .traffic-merah {{ background:var(--danger-fill); }}
  .grid2 {{ display:grid; grid-template-columns: 1fr 1fr; gap:10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th, td {{ text-align:left; padding:6px 4px; border-bottom:0.5px solid var(--border); }}
  th {{ color:var(--muted); font-weight:500; }}
  .disclaimer {{ font-size:11px; color:var(--tiny); margin-top:24px; padding-top:12px; border-top:0.5px solid var(--border); }}
</style>
</head>
<body>

<h1>Regime Screener</h1>
<p class="subtitle">Diperbarui: {DATA['generated_at'][:16].replace('T',' ')}</p>

<h2>Tahap 1 &mdash; Status IHSG</h2>
<div class="card">
  <div class="row-between">
    <span class="ticker"><span class="traffic traffic-{light}"></span>{fase_label}</span>
    <span class="badge badge-{fase_color}">{DATA['ihsg']['pct_dari_trough_%']:+.1f}% dari bottom</span>
  </div>
  <p class="muted">Harga: {DATA['ihsg']['harga']:.0f} &middot; Drawdown dari puncak 52w: {DATA['ihsg']['drawdown_dari_puncak_52w_%']:.1f}%</p>
  <p class="muted">{light_note}</p>
</div>

<table>
  <tr><th>Horizon</th><th>Rata² return</th><th>% Positif</th><th>Terburuk</th><th>MAE rata²</th></tr>
  {render_backtest_table()}
</table>
<p class="tiny-muted">Base rate dari {DATA['backtest_summary'][0]['n_sampel']} episode bear market IHSG sejak 2000 -- bukan prediksi pasti.</p>

<h2>Tahap 2 &mdash; Status Sektor</h2>
<div class="grid2">
{render_sector_cards()}
</div>

<h2>Tahap 3 &mdash; Kandidat Emiten</h2>
{render_candidate_cards()}

<h2>Tahap 4 &mdash; Bobot Ekuitas</h2>
{render_equity_card()}

<div class="disclaimer">
  Universe saat ini: basket representatif per sektor (belum universe 840 emiten penuh).
  Data historis, bukan sinyal beli/jual. Bukan nasihat keuangan.
</div>

</body>
</html>"""

with open("dashboard.html", "w") as f:
    f.write(HTML)
print("dashboard.html dibuat.")
