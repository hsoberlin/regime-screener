"""
app.py -- Regime Screener (Streamlit)
Menarik data live tiap dibuka (di-cache 15 menit supaya tidak spam Yahoo Finance
tiap interaksi UI). Butuh engine.py, universe.py, backtest_regime.py di folder
yang sama (atau di root repo yang sama) supaya import di bawah berhasil.
"""

import streamlit as st
from datetime import datetime

from engine import run as run_engine

st.set_page_config(page_title="Regime Screener", layout="centered")

FASE_LABEL = {
    "BEAR (belum rebound 20%)": "BEAR",
    "BOTTOM-REBOUND (terkonfirmasi)": "BOTTOM-REBOUND",
    "NORMALIZING": "NORMALIZING",
    "NORMAL (tidak dalam bear market >=20%)": "NORMAL",
}

TIER_LABEL = {
    "kandidat_kuat": "Kandidat kuat",
    "menunggu_konfirmasi": "Menunggu konfirmasi",
    "gap_tidak_signifikan": "Gap tidak signifikan",
}


@st.cache_data(ttl=900)  # cache 15 menit -- sesuaikan kalau mau lebih/kurang sering
def load_data():
    return run_engine()


def traffic_light(fase, backtest):
    if fase.startswith("BOTTOM-REBOUND"):
        return "🟢", "Fase rebound awal — syarat sektor & saham aktif dicari"
    if fase == "NORMALIZING":
        b40 = next((b for b in backtest if b["horizon_hari"] == 40), None)
        if b40 and b40["pct_positif"] >= 70:
            return "🟡", "Sudah lewat fase awal (>20% dari bottom) — masih ada peluang tapi tidak seoptimal fase rebound awal"
        return "🟡", "Fase transisi — perlu lebih selektif"
    if fase.startswith("BEAR"):
        return "🔴", "Masih tren turun, belum ada konfirmasi rebound"
    return "🔴", "Tidak ada bear market aktif — strategi ini dirancang khusus untuk fase bottom-rebound"


# ---------------------------------------------------------------------------
st.title("Regime Screener")

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()

try:
    with st.spinner("Menarik data IHSG & universe saham..."):
        data = load_data()
except Exception as e:
    st.error(
        "Gagal menarik data dari Yahoo Finance setelah beberapa percobaan. "
        "Ini biasanya sementara -- Yahoo Finance kadang rate-limit IP server cloud. "
        "Coba klik 'Refresh data' di atas dalam beberapa menit."
    )
    st.caption(f"Detail teknis: {e}")
    st.stop()

st.caption(f"Diperbarui: {data['generated_at'][:16].replace('T', ' ')}")

# Tahap 1 -- IHSG
st.subheader("Tahap 1 — Status IHSG")
fase_raw = data["ihsg"]["fase"]
light, note = traffic_light(fase_raw, data["backtest_summary"])
fase_label = FASE_LABEL.get(fase_raw, fase_raw)

c1, c2, c3 = st.columns(3)
c1.metric("Fase", f"{light} {fase_label}")
c2.metric("Harga IHSG", f"{data['ihsg']['harga']:.0f}")
c3.metric("Dari bottom", f"{data['ihsg']['pct_dari_trough_%']:+.1f}%")
st.caption(note)

with st.expander("Backtest probabilitas historis (7 episode sejak 2000)"):
    st.dataframe(
        [{"Horizon": f"{b['horizon_hari']}h", "Rata² return": f"{b['rata_rata_return_%']:+.1f}%",
          "% Positif": f"{b['pct_positif']:.0f}%", "Terburuk": f"{b['worst_return_%']:+.1f}%",
          "MAE rata²": f"{b['rata_rata_MAE_%']:+.1f}%"} for b in data["backtest_summary"]],
        hide_index=True, use_container_width=True,
    )

# Tahap 2 -- Sektor
st.subheader("Tahap 2 — Status Sektor")
for s in data["sektor"]:
    status = "🟢 Sudah bergerak" if s["sudah_bergerak"] else "⚪ Belum bergerak"
    st.write(f"**#{s['ranking']} {s['sektor']}** — {s['return_sejak_bottom_pct']:+.1f}% ({s['n_saham']} saham) · {status}")

# Tahap 3 -- Kandidat Emiten
st.subheader("Tahap 3 — Kandidat Emiten")
alokasi_tickers = {a["ticker"] for a in data["bobot_ekuitas"].get("alokasi", [])}
kandidat_menunggu = set(data["bobot_ekuitas"].get("kandidat_menunggu", []))

shown = [c for c in data["kandidat"] if c["tier"] in ("kandidat_kuat", "menunggu_konfirmasi")]
if not shown:
    st.info("Tidak ada kandidat lolos gerbang saat ini.")
for c in shown:
    if c["ticker"] in alokasi_tickers:
        badge = "🟢 All-in Rp20jt"
    elif c["ticker"] in kandidat_menunggu:
        badge = "🟡 Cash ditahan"
    else:
        badge = TIER_LABEL.get(c["tier"], c["tier"])

    with st.container(border=True):
        st.write(f"**{c['ticker']}** — {badge}")
        m = c["metrics"]
        st.caption(
            f"{c['sektor']} · Gap vs sektor {m['gap_vs_sektor_pct']:+.1f}% · "
            f"Vol {m['vol_ratio_today']:.1f}x · Value Rp{m['value_sesi_ini_idr']/1e9:.0f}M"
        )
        if c["penalty_reasons"]:
            st.caption(f"⚠️ Berat naik: {', '.join(c['penalty_reasons'])}")
        if c["ticker"] in alokasi_tickers:
            st.line_chart(m["harga_20h"], height=120)

# Tahap 4 -- Bobot Ekuitas
st.subheader("Tahap 4 — Bobot Ekuitas")
eq = data["bobot_ekuitas"]
status_icon = {"all_in": "🟢", "cash_ditahan": "🟡", "cash_menganggur": "⚪"}
st.write(f"{status_icon.get(eq['status'], '')} **{eq['status'].replace('_', ' ').title()}**")
st.caption(eq["detail"])

st.divider()
st.caption(
    "Universe saat ini: basket representatif per sektor (belum universe 840 emiten penuh). "
    "Data historis, bukan sinyal beli/jual. Bukan nasihat keuangan."
)
