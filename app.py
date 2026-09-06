"""
COMPOUNDING SCREENER
====================
Peleburan Wyckoff (No Supply), Turtle (Disiplin), dan Regime (Laggard Gap).
Fokus: Mencari saham Fase 1-2 (bertahan di atas Lowest Low 20) dengan indikasi 
No Supply (Volume MA10/MA30 < 1.0) dan momentum segar (Stochastic K < 80).
Dilengkapi deteksi Fase Kenaikan dan jarak dari dasar 120 hari ke belakang.

Jalankan: streamlit run compounding_screener.py
Kebutuhan: streamlit yfinance pandas numpy plotly
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from datetime import timedelta, timezone

st.set_page_config(page_title="Compounding Screener", layout="wide")
WIB = timezone(timedelta(hours=7))

# =====================================================================
# TEMA VISUAL (Dark Clean)
# =====================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #101014;
  --card: #1A1A20;
  --card-line: #2C2C35;
  --accent: #B8823D;
  --text: #E0E0E5;
  --text-dim: #8B8B99;
  --green: #4E9F3D;
  --red: #D9534F;
  --warn: #E2B93B;
}

.stApp { background-color: var(--bg); }
.stApp, .stApp p, .stApp span, .stApp div { color: var(--text); }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; color: var(--text) !important; }
[data-testid="stMetricValue"], code, .stMarkdown code { font-family: 'IBM Plex Mono', monospace !important; }

.compounding-card {
  background: var(--card); border: 1px solid var(--card-line);
  padding: 16px; border-radius: 8px; margin-bottom: 12px;
  border-left: 4px solid var(--accent);
}
.compounding-title { font-family: 'Space Grotesk', sans-serif; font-size: 20px; font-weight: 700; }
.badge {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  padding: 4px 10px; border-radius: 12px; margin-left: 8px;
}
.badge-sektor { background: rgba(184, 130, 61, 0.15); color: var(--accent); border: 1px solid rgba(184, 130, 61, 0.3); }
.badge-fase-aman { background: rgba(78, 159, 61, 0.15); color: var(--green); border: 1px solid rgba(78, 159, 61, 0.3); }
.badge-fase-bahaya { background: rgba(217, 83, 79, 0.15); color: var(--red); border: 1px solid rgba(217, 83, 79, 0.3); }

.metric-row { display: flex; gap: 15px; margin-top: 10px; flex-wrap: wrap; }
.metric-item { font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: var(--text-dim); }
.metric-val { color: var(--text); font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# PARAMETER SISTEM
# =====================================================================
MIN_LIQUIDITY = 1_000_000_000  # Rp 1 Miliar
VOL_RATIO_MAX = 1.0            # VMA10 / VMA30
STOCH_K_MAX = 80               # Batas overbought
LL_PERIOD = 20                 # Lowest Low 20 hari (Batas SL)
LOOKBACK_PHASE = 120           # 120 hari ke belakang untuk Titik Nol Fase
TROUGH_DATE = pd.Timestamp("2026-06-08") # Untuk Gap Sektoral

# =====================================================================
# FUNGSI PERHITUNGAN
# =====================================================================
@st.cache_data(ttl=900, show_spinner=False)
def fetch_market_data(tickers, period="6mo"):
    tickers_jk = [f"{t}.JK" for t in tickers]
    try:
        df = yf.download(tickers_jk, period=period, interval="1d", 
                         progress=False, group_by="ticker", threads=True)
        return df
    except Exception as e:
        st.error(f"Gagal menarik data: {e}")
        return None

def calculate_stochastic(high, low, close, k_window=14):
    lowest_low = low.rolling(window=k_window).min()
    highest_high = high.rolling(window=k_window).max()
    stoch_k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    return stoch_k

def hitung_fase_wyckoff(low_series):
    if len(low_series) < 60:
        return 0
        
    low_120 = low_series.tail(LOOKBACK_PHASE)
    ground_zero_idx = low_120.argmin()
    ground_zero_val = low_120.iloc[ground_zero_idx]
    
    low_after_gz = low_120.iloc[ground_zero_idx:]
    if len(low_after_gz) < 10:
        return 0
        
    swing_lows = []
    for i in range(4, len(low_after_gz) - 4):
        window = low_after_gz.iloc[i-4:i+5]
        if low_after_gz.iloc[i] == window.min():
            swing_lows.append(low_after_gz.iloc[i])
            
    fase = 0
    last_sl = ground_zero_val
    for sl in swing_lows:
        if sl > last_sl:
            fase += 1
            last_sl = sl
        elif sl < last_sl:
            fase = 0
            last_sl = sl
            
    return fase

def analyze_stock(df_stock, ticker):
    if df_stock is None or len(df_stock.dropna()) < 35:
        return None
        
    close = df_stock['Close'].dropna()
    high = df_stock['High'].dropna()
    low = df_stock['Low'].dropna()
    volume = df_stock['Volume'].dropna()
    
    common_idx = close.index.intersection(volume.index)
    close, high, low, volume = close[common_idx], high[common_idx], low[common_idx], volume[common_idx]
    
    if len(close) < 35:
        return None

    # 1. Likuiditas (Value 20 hari rata-rata)
    value_daily = close * volume
    val_ma20 = value_daily.rolling(20).mean().iloc[-1]
    
    # 2. Batas Fase & Cut Loss (Lowest Low 20 hari)
    ll20 = low.shift(1).rolling(LL_PERIOD).min().iloc[-1]
    close_now = close.iloc[-1]
    retrace_sehat = close_now >= ll20
    
    # 3. No Supply (Volume Ratio)
    vma10 = volume.rolling(10).mean().iloc[-1]
    vma30 = volume.rolling(30).mean().iloc[-1]
    vol_ratio = vma10 / vma30 if vma30 > 0 else 999
    
    # 4. Momentum (Stochastic)
    stoch_k_series = calculate_stochastic(high, low, close)
    stoch_k = stoch_k_series.iloc[-1]
    
    # 5. Penghitungan Fase
    fase_aktif = hitung_fase_wyckoff(low)
    
    # 6. Kenaikan dari bottom 120 Hari
    bottom_120 = low.tail(LOOKBACK_PHASE).min()
    pct_from_bottom_120 = ((close_now - bottom_120) / bottom_120) * 100
    
    # Gap Sektoral (Return sejak bottom IHSG 8 Juni 2026)
    close_after_trough = close[close.index >= TROUGH_DATE]
    if len(close_after_trough) > 0:
        ret_from_trough = (close_now - close_after_trough.iloc[0]) / close_after_trough.iloc[0] * 100
    else:
        ret_from_trough = 0

    return {
        "ticker": ticker,
        "close": float(close_now),
        "val_ma20": float(val_ma20),
        "ll20": float(ll20),
        "retrace_sehat": retrace_sehat,
        "vol_ratio": float(vol_ratio),
        "stoch_k": float(stoch_k),
        "fase": fase_aktif,
        "pct_from_bottom_120": float(pct_from_bottom_120),
        "ret_from_trough": float(ret_from_trough),
        "price_history": close.tail(45).tolist()
    }

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sectors_for_candidates(tickers):
    sector_map = {}
    for t in tickers:
        try:
            info = yf.Ticker(f"{t}.JK").info
            sector_map[t] = info.get("sector", "Unmapped")
        except:
            sector_map[t] = "Unmapped"
    return sector_map

# =====================================================================
# ANTARMUKA APLIKASI
# =====================================================================
st.title("Compounding Screener")
st.markdown("Peleburan strategi **No Supply (Wyckoff)**, disiplin **Turtle**, dan **Regime Sektoral**.")

# Sidebar Setup
st.sidebar.markdown("### ⚙️ Universe Setup")
universe_input = st.sidebar.text_area(
    "Daftar Ticker:",
    value="BBCA, BBRI, BMRI, BBNI, BRIS, AMMN, TPIA, BREN, BYAN, ASII, \nTLKM, UNTR, ICBP, MYOR, INCO, ANTM, PTBA, ADRO, TINS, HRTA, \nEMAS, SSMS, TOWR, AADI, CYBR, EPAC, MBSS, MUTU, GPRA, TBIG, REAL",
    height=150
)
tickers_raw = [t.strip().upper() for t in universe_input.replace('\n', ',').split(',') if t.strip()]
TICKERS = list(set(tickers_raw))

st.sidebar.markdown(f"**Total Ticker:** {len(TICKERS)}")

if st.button("🚀 Jalankan Screener"):
    if not TICKERS:
        st.warning("Masukkan setidaknya 1 ticker.")
        st.stop()
        
    with st.spinner(f"Menarik harga & volume {len(TICKERS)} saham..."):
        df_market = fetch_market_data(TICKERS)
        
    if df_market is None:
        st.stop()

    candidates_raw = []
    
    with st.spinner("Memproses Gerbang Keras & Pendeteksi Fase..."):
        for t in TICKERS:
            if isinstance(df_market.columns, pd.MultiIndex):
                if f"{t}.JK" in df_market.columns.get_level_values(0):
                    df_stock = df_market[f"{t}.JK"]
                else: continue
            else:
                df_stock = df_market
                
            metrics = analyze_stock(df_stock, t)
            if not metrics: continue
                
            if metrics["val_ma20"] < MIN_LIQUIDITY: continue
            if not metrics["retrace_sehat"]: continue
            if metrics["stoch_k"] >= STOCH_K_MAX: continue
            if metrics["vol_ratio"] >= VOL_RATIO_MAX: continue
            
            candidates_raw.append(metrics)

    if not candidates_raw:
        st.info("Tidak ada saham yang lolos semua gerbang (Likuiditas, LL20, Stoch < 80, No Supply).")
        st.stop()

    with st.spinner("Menarik label sektor & menghitung Gap..."):
        valid_tickers = [c["ticker"] for c in candidates_raw]
        sector_map = fetch_sectors_for_candidates(valid_tickers)
        
        sector_returns = {}
        for c in candidates_raw:
            skt = sector_map[c["ticker"]]
            sector_returns.setdefault(skt, []).append(c["ret_from_trough"])
            
        sector_avg_map = {skt: np.mean(rets) for skt, rets in sector_returns.items()}
        
        for c in candidates_raw:
            skt = sector_map[c["ticker"]]
            c["sektor"] = skt
            c["sector_avg"] = sector_avg_map[skt]
            c["gap_sektoral"] = c["ret_from_trough"] - c["sector_avg"]

    candidates_raw.sort(key=lambda x: (x["fase"], x["vol_ratio"]))

    st.subheader(f"🎯 {len(candidates_raw)} Kandidat Compounding")
    st.caption("Sizing: 30% di awal, +70% jika retrace tetap di atas LL20 dan Oversold (Stochastic < 80).")
    
    for c in candidates_raw:
        gap_color = "var(--red)" if c["gap_sektoral"] < 0 else "var(--green)"
        stoch_color = "var(--green)" if c["stoch_k"] < 30 else "var(--text)"
        
        fase_label = "Awal (Fresh)" if c["fase"] <= 1 else ("Lanjutan" if c["fase"] == 2 else "RAWAN (Bahaya)")
        badge_fase_class = "badge-fase-aman" if c["fase"] <= 2 else "badge-fase-bahaya"
        
        fig = go.Figure(go.Scatter(y=c["price_history"], mode='lines', line=dict(color='#B8823D', width=2)))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=50, width=150,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          xaxis=dict(visible=False), yaxis=dict(visible=False))

        st.markdown(f"""
        <div class="compounding-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span class="compounding-title">{c['ticker']}</span>
                    <span class="badge badge-sektor">{c['sektor']}</span>
                    <span class="badge {badge_fase_class}">Fase {c['fase']} : {fase_label}</span>
                </div>
            </div>
            <div class="metric-row">
                <div class="metric-item">Vol Ratio: <span class="metric-val" style="color:var(--green)">{c['vol_ratio']:.2f}x</span></div>
                <div class="metric-item">Stochastic K: <span class="metric-val" style="color:{stoch_color}">{c['stoch_k']:.1f}</span></div>
                <div class="metric-item">Value 20H: <span class="metric-val">Rp {c['val_ma20']/1e9:.1f} Miliar</span></div>
                <div class="metric-item">Batas SL (LL20): <span class="metric-val" style="color:var(--red)">{c['ll20']:,.0f}</span></div>
                <div class="metric-item">Dari Dasar 120H: <span class="metric-val" style="color:var(--green)">+{c['pct_from_bottom_120']:.1f}%</span></div>
                <div class="metric-item">Gap Sektor: <span class="metric-val" style="color:{gap_color}">{c['gap_sektoral']:+.1f}%</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.plotly_chart(fig, use_container_width=False, config={'displayModeBar': False})
