"""
COMPOUNDING SCREENER & SWING CYCLE
==================================
Sistem penyaringan saham berbasis siklus:
1. Tahap 0: Likuiditas >= Rp1M & Detak Jantung (Range) >= 5%
2. Tahap 1: Wyckoff Absorption (Close >= LL20 & Vol Ratio < 1.0)
3. Tahap 2: Pembagian Keranjang (Keranjang 30% Breakout vs Keranjang 70% Retrace Oversold)

Jalankan: streamlit run compounding_screener.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from datetime import timedelta, timezone

st.set_page_config(page_title="Compounding Screener", layout="wide", initial_sidebar_state="expanded")
WIB = timezone(timedelta(hours=7))

# =====================================================================
# TEMA VISUAL UI
# =====================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #101014;
  --card: #1A1A20;
  --card-line: #2C2C35;
  --accent-1: #B8823D;
  --accent-2: #5C8BC6;
  --text: #E0E0E5;
  --text-dim: #8B8B99;
  --green: #4E9F3D;
  --red: #D9534F;
}

.stApp { background-color: var(--bg); }
.stApp, .stApp p, .stApp span, .stApp div { color: var(--text); }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; color: var(--text) !important; }
[data-testid="stMetricValue"], code, .stMarkdown code { font-family: 'IBM Plex Mono', monospace !important; }

.card-breakout {
  background: var(--card); border: 1px solid var(--card-line);
  padding: 16px; border-radius: 8px; margin-bottom: 12px;
  border-left: 4px solid var(--accent-1);
}
.card-retrace {
  background: var(--card); border: 1px solid var(--card-line);
  padding: 16px; border-radius: 8px; margin-bottom: 12px;
  border-left: 4px solid var(--accent-2);
}

.stock-title { font-family: 'Space Grotesk', sans-serif; font-size: 22px; font-weight: 700; }
.badge {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  padding: 4px 10px; border-radius: 12px; margin-left: 8px;
}
.badge-sektor { background: rgba(255, 255, 255, 0.05); color: var(--text-dim); border: 1px solid rgba(255,255,255,0.1); }
.badge-fase { background: rgba(184, 130, 61, 0.15); color: var(--accent-1); border: 1px solid rgba(184, 130, 61, 0.3); }

.metric-row { display: flex; gap: 15px; margin-top: 10px; flex-wrap: wrap; }
.metric-item { font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: var(--text-dim); }
.metric-val { color: var(--text); font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# PARAMETER SISTEM MUTLAK
# =====================================================================
MIN_LIQUIDITY = 1_000_000_000  # Rp 1 Miliar
MIN_HEARTBEAT = 0.05           # 5% rentang harga 20H
VOL_RATIO_MAX = 1.0            # VMA10 / VMA30
STOCH_OVERSOLD = 30            # Batas Oversold untuk Retrace Entry
LL_PERIOD = 20                 # Jendela Turtle (20 Hari)
LOOKBACK_PHASE = 120           # 120 hari untuk menghitung fase makro
TROUGH_DATE = pd.Timestamp("2026-06-08") # Bottom IHSG

# =====================================================================
# DATA TICKER BEI (750+ SAHAM)
# =====================================================================
IDX_TICKERS_ALL = """AALI, ABBA, ABDA, ABMM, ACES, ACST, ADCP, ADES, ADHI, ADMF, ADRO, AGII, AGRO, AIMS, AISA, AKPI, AKRA, AKSI, ALDO, ALKA, ALMI, ALTO, AMAG, AMAN, AMAR, AMFG, AMIN, AMMN, AMRT, ANDI, ANJT, ANTM, APEX, APIC, APII, APLN, ARCI, ARGO, ARII, ARKA, ARKO, ARNA, ARTA, ARTI, ASBI, ASGR, ASHA, ASII, ASJT, ASLC, ASMI, ASRI, ASSA, AUTO, AYLS, BABP, BACA, BAEK, BAPA, BAPI, BATA, BAJA, BALI, BANK, BBYB, BBCA, BBHI, BBKP, BBLD, BBMD, BBNI, BBRI, BBRM, BBTN, BCAP, BCIC, BCPJ, BDMN, BEKS, BELL, BESS, BEST, BFIN, BGTG, BHIT, BIKA, BINA, BINN, BIPI, BIPP, BIRD, BISI, BKDP, BKSL, BKSW, BLTA, BLTZ, BMAS, BMSR, BMTR, BNBA, BNBR, BNGA, BNII, BNLI, BOBA, BOGA, BOLA, BPFI, BPRS, BPTN, BRAM, BRIS, BRMS, BRNA, BRPT, BSDE, BSIM, BSLC, BSML, BSWD, BTEK, BTEL, BTPS, BUKA, BULL, BUMI, BVIC, BWPT, BYAN, CAKK, CAMP, CANI, CARS, CASA, CASH, CASS, CBPE, CBRE, CCSI, CEKA, CENT, CFIN, CGAS, CHIP, CINT, CITA, CITY, CLAY, CLEO, CLPI, CMNP, CMPP, CMRY, CNKO, CNMT, CNTX, COAL, COCO, CPIN, CPRI, CPRO, CRAB, CSAP, CSIS, CSMI, CTBN, CTRA, DADA, DART, DAYA, DCII, DEAL, DEFI, DEWA, DGIK, DILD, DIVA, DKFT, DLTA, DMAS, DMMX, DMND, DNA, DNET, DOID, DPUM, DSFI, DSNG, DSSA, DUCK, DUTI, DVLA, DWGL, DYAN, EAST, ECII, EDSA, EFIN, EKAD, ELSA, ELTY, EMDE, EMTK, ENRG, ENVY, EPMT, ERAA, ERAL, ERAY, ERTX, ESIP, ESSA, ESTA, ESTI, ETWA, EXCL, FAAE, FAIL, FAPA, FAST, FASW, FENI, FIIT, FILA, FINA, FIRE, FIT, FITT, FLMC, FMII, FOOD, FORU, FOS, FPNI, FREN, GAMA, GAPP, GATA, GDST, GDYR, GEMA, GEMS, GGRM, GHCO, GIAA, GJTL, GLOB, GLVA, GMFI, GMTD, GOLD, GOLL, GOOD, GOTO, GPRA, GSMF, GTBO, GWSA, GZCO, HADE, HAIS, HALO, HAMP, HANS, HDFA, HDIT, HEAL, HELI, HERO, HEXA, HITS, HKMU, HMSP, HOKI, HOME, HOMI, HRME, HRTA, HRUM, IATA, IBC, IBST, ICBP, ICON, IDEA, IDPR, IDSR, IFII, IGAR, IIKP, IKAI, IKAN, IKBI, IMAS, IMJS, IMPC, INAF, INAI, INCF, INCI, INCO, INDF, INDO, INDR, INDX, INDY, INFA, INFO, INKP, INOV, INPC, INPP, INPS, INRU, INTA, INTD, INTP, IPCC, IPCM, IPOL, IPPE, IPMG, IRRA, ISAT, ISPA, ITIC, ITMA, ITMG, JAST, JAWA, JAYA, JCON, JGLE, JIHD, JKON, JKSW, JMAS, JPFA, JPTU, JRSK, JSKY, JSMR, JSPT, JTPE, KAEF, KARW, KAST, KBLI, KBLM, KBLV, KBRI, KDSI, KEEN, KEJU, KIAS, KICI, KIJA, KIN, KINO, KION, KIOS, KJA, KKGI, KLBF, KMDS, KOBX, KOIN, KOKA, KONI, KOPI, KOTA, KPAL, KPIG, KRAH, KRAS, KREN, KUAS, LAA, LABA, LAND, LAPD, LCKM, LCPI, LEAD, LENG, LHKI, LION, LMAS, LMPI, LMSH, LPCK, LPF, LPIN, LPKR, LPLI, LPPF, LPPS, LRNA, LSIP, LTLS, LUCK, LUSK, MABA, MACA, MAGE, MAGP, MAIN, MAJA, MAKO, MAMI, MAPA, MAPB, MAPI, MARI, MARK, MASA, MAST, MAYA, MBAP, MBC, MBSS, MBTO, MCAS, MCOR, MDIA, MDKA, MDLN, MDRN, MEDC, MEGA, MERK, META, MFAC, MFAM, MFIN, MFMI, MGNA, MGRO, MICE, MIDI, MIKA, MINA, MIRA, MITI, MKNT, MKPI, MLBI, MLIA, MLPL, MLPT, MMDC, MMND, MNCN, MOLI, MOMS, MOPA, MPAP, MPAS, MPIL, MPMR, MPPA, MPPO, MREI, MSIN, MSKY, MTDL, MTFN, MTLA, MTPS, MTRA, MTSM, MTYA, MTYI, MUGI, MUTU, MYOH, MYOR, MYRX, MYTX, NAGA, NALA, NANO, NASA, NASI, NAYZ, NCKL, NELY, NETA, NFCX, NICK, NICL, NIRO, NISP, NOBU, NRCE, NUSA, NUWA, NYAN, NZIA, OASA, OBMD, OCBC, OILS, OKAS, OMIR, OMMO, OMO, OPMS, OPTI, PADI, PAMA, PAMI, PAMP, PANR, PANS, PAOS, PBB, PBRX, PBSA, PCAR, PDES, PEGE, PEHA, PELN, PERC, PGAS, PGEO, PGLI, PGRM, PICR, PIIT, PINO, PJAA, PKPK, PLAS, PLIN, PLNC, PLSS, PMJS, PMPP, PNBN, PNBS, PNLF, PNSE, PNTX, POLA, POLI, POLL, POLU, POLY, POOL, PORT, POSA, POWR, PPGL, PPRE, PPRO, PRAS, PRIM, PRIT, PROS, PSAB, PSAK, PSGO, PSKT, PTBA, PTIS, PTMP, PTPP, PTRO, PTSN, PTSP, PUDP, PUKA, PULL, PURE, PUTI, PWON, PYFA, PZZA, RAJA, RALS, RANC, RBMS, RCCC, RDTX, REAL, REFI, RELI, RMBA, RODA, ROMA, RONY, ROSI, ROST, RSGK, SAGE, SAME, SAMF, SAPX, SCCO, SCMA, SCPI, SCTV, SDMU, SDPC, SDRA, SECT, SEJA, SEMA, SHID, SIDO, SILO, SIMA, SIMP, SINI, SION, SIPD, SIPL, SKBM, SKLT, SKRN, SKYB, SMAR, SMBR, SMCB, SMDR, SMGR, SMIL, SMKL, SMMA, SMRA, SMTK, SNLK, SOBI, SOGM, SONA, SOSS, SOTG, SOTO, SPMA, SQMI, SRA, SRAJ, SRBM, SREI, SRIL, SRTG, SSIA, SSMS, SSTM, STAR, STTP, SUCB, SUGI, SULA, SULI, SUMA, SUPR, SURA, SWAT, SWMT, SYAR, TAFG, TAMA, TAMU, TARA, TAXI, TBIG, TBLA, TCID, TCPI, TEBE, TECH, TELE, TFCO, TGKA, TIFA, TIGM, TINS, TIRA, TIRT, TKIM, TLDN, TLKM, TMAS, TMPO, TOBA, TOPO, TOTO, TOWR, TPIA, TRAM, TRIL, TRIN, TRIO, TRIS, TRJA, TRST, TRUE, TRUK, TSPC, TUGU, TURI, TYRE, UCID, UANG, UKMN, ULTJ, UNIC, UNIQ, UNIT, UNTR, UNVR, UPPF, URBN, USUP, VIC, VICO, VINS, VIRT, VIVA, VKKI, VOKS, VRNA, VTNY, WAPO, WARR, WEGE, WICO, WIDA, WIFI, WIIA, WIKA, WIM, WIPO, WIRG, WMPP, WMUU, WOMF, WOOD, WOWS, WSBP, WSKT, WTON, WZMA, YELO, YPAS, YULE, ZATA, ZBRA, ZINC, ZYRX"""

# =====================================================================
# ENGINE PERHITUNGAN
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
    if len(low_series) < 60: return 0
    low_120 = low_series.tail(LOOKBACK_PHASE)
    ground_zero_idx = low_120.argmin()
    ground_zero_val = low_120.iloc[ground_zero_idx]
    
    low_after_gz = low_120.iloc[ground_zero_idx:]
    if len(low_after_gz) < 10: return 0
        
    swing_lows = []
    for i in range(5, len(low_after_gz) - 5):
        window = low_after_gz.iloc[i-5:i+6]
        if low_after_gz.iloc[i] == window.min():
            swing_lows.append(low_after_gz.iloc[i])
            
    fase = 0
    last_sl = ground_zero_val
    for sl in swing_lows:
        if sl > last_sl * 1.02:
            fase += 1
            last_sl = sl
        elif sl < last_sl:
            fase = 0
            last_sl = sl
    return fase

def analyze_stock(df_stock, ticker):
    if df_stock is None or len(df_stock.dropna()) < 35: return None
        
    close = df_stock['Close'].dropna()
    high = df_stock['High'].dropna()
    low = df_stock['Low'].dropna()
    volume = df_stock['Volume'].dropna()
    
    common_idx = close.index.intersection(volume.index)
    close, high, low, volume = close[common_idx], high[common_idx], low[common_idx], volume[common_idx]
    if len(close) < 35: return None

    # TAHAP 0: LIKUIDITAS & DETAK JANTUNG
    val_ma20 = (close * volume).rolling(20).mean().iloc[-1]
    hh20_series = high.shift(1).rolling(LL_PERIOD).max()
    ll20_series = low.shift(1).rolling(LL_PERIOD).min()
    hh20 = hh20_series.iloc[-1]
    ll20 = ll20_series.iloc[-1]
    close_now = close.iloc[-1]
    heartbeat_range = (hh20 - ll20) / ll20 if ll20 > 0 else 0

    # TAHAP 1: SETUP ABSORPTION
    vma10 = volume.rolling(10).mean().iloc[-1]
    vma30 = volume.rolling(30).mean().iloc[-1]
    vol_ratio = vma10 / vma30 if vma30 > 0 else 999
    struktur_aman = close_now >= ll20

    # TAHAP 2: KERANJANG AKSI
    stoch_k_series = calculate_stochastic(high, low, close)
    stoch_k = stoch_k_series.iloc[-1]
    
    past_20_closes = close.iloc[-20:]
    past_20_hh20s = hh20_series.iloc[-20:]
    has_breakout_history = any(past_20_closes >= past_20_hh20s)
    
    is_breakout = close_now >= hh20
    is_retrace = (close_now < hh20) and (stoch_k <= STOCH_OVERSOLD) and has_breakout_history

    fase_aktif = hitung_fase_wyckoff(low)
    bottom_120 = low.tail(LOOKBACK_PHASE).min()
    pct_from_bottom_120 = ((close_now - bottom_120) / bottom_120) * 100 if bottom_120 > 0 else 0
    
    close_after_trough = close[close.index >= TROUGH_DATE]
    ret_from_trough = ((close_now - close_after_trough.iloc[0]) / close_after_trough.iloc[0] * 100) if len(close_after_trough) > 0 else 0

    return {
        "ticker": ticker, "close": float(close_now), "val_ma20": float(val_ma20),
        "hh20": float(hh20), "ll20": float(ll20), "heartbeat": float(heartbeat_range),
        "struktur_aman": struktur_aman, "vol_ratio": float(vol_ratio), "stoch_k": float(stoch_k),
        "has_breakout_history": has_breakout_history, "is_breakout": is_breakout, "is_retrace": is_retrace,
        "fase": fase_aktif, "pct_from_bottom_120": float(pct_from_bottom_120),
        "ret_from_trough": float(ret_from_trough), "price_history": close.tail(45).tolist()
    }

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sectors(tickers):
    sector_map = {}
    for t in tickers:
        try:
            sector_map[t] = yf.Ticker(f"{t}.JK").info.get("sector", "Unmapped")
        except:
            sector_map[t] = "Unmapped"
    return sector_map

# =====================================================================
# ANTARMUKA APLIKASI
# =====================================================================
st.title("Compounding Screener 🎯")
st.markdown("Sistem penyaringan *Swing Cycle* berbasis likuiditas, *Wyckoff Absorption*, dan disiplin *Turtle*.")

st.sidebar.markdown("### ⚙️ Universe Input")
universe_input = st.sidebar.text_area(
    "Daftar Ticker BEI (Default: 750+ Saham):",
    value=IDX_TICKERS_ALL,
    height=250
)
tickers_raw = [t.strip().upper() for t in universe_input.replace('\n', ',').split(',') if t.strip()]
TICKERS = list(set(tickers_raw))

if st.button("🚀 Pindai Seluruh Pasar"):
    if not TICKERS:
        st.stop()
        
    with st.spinner(f"Menarik & menganalisis {len(TICKERS)} saham dari Yahoo Finance (Mohon tunggu 1-2 menit)..."):
        df_market = fetch_market_data(TICKERS)
    if df_market is None: st.stop()

    k_breakout, k_retrace = [], []
    
    for t in TICKERS:
        df_stock = df_market[f"{t}.JK"] if isinstance(df_market.columns, pd.MultiIndex) and f"{t}.JK" in df_market.columns.get_level_values(0) else df_market if not isinstance(df_market.columns, pd.MultiIndex) else None
        if df_stock is None: continue
            
        m = analyze_stock(df_stock, t)
        if not m: continue
            
        if m["val_ma20"] < MIN_LIQUIDITY: continue
        if m["heartbeat"] < MIN_HEARTBEAT: continue
        if not m["struktur_aman"]: continue
        if m["vol_ratio"] >= VOL_RATIO_MAX: continue
        
        if m["is_breakout"]:
            k_breakout.append(m)
        elif m["is_retrace"]:
            k_retrace.append(m)

    if not k_breakout and not k_retrace:
        st.warning("Tidak ada saham yang lolos filter sistem hari ini.")
        st.stop()

    valid_tickers = [c["ticker"] for c in k_breakout + k_retrace]
    with st.spinner("Memetakan Sektor..."):
        sector_map = fetch_sectors(valid_tickers)
        sector_returns = {}
        for c in k_breakout + k_retrace:
            skt = sector_map[c["ticker"]]
            sector_returns.setdefault(skt, []).append(c["ret_from_trough"])
        sector_avg_map = {skt: np.mean(rets) for skt, rets in sector_returns.items()}
        
        for c in k_breakout + k_retrace:
            skt = sector_map[c["ticker"]]
            c["sektor"] = skt
            c["gap_sektoral"] = c["ret_from_trough"] - sector_avg_map[skt]

    k_breakout.sort(key=lambda x: x["vol_ratio"])
    k_retrace.sort(key=lambda x: x["stoch_k"])

    st.divider()

    st.subheader(f"🛒 Keranjang 1: Fase Breakout ({len(k_breakout)} Saham)")
    st.caption("Aksi: Entry awal 30%. Syarat: Terbukti ada jejak No Supply dan hari ini menembus Highest High 20 (HH20).")
    for c in k_breakout:
        fig = go.Figure(go.Scatter(y=c["price_history"], mode='lines', line=dict(color='#B8823D', width=2)))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=50, width=150, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(visible=False))
        
        st.markdown(f"""
        <div class="card-breakout">
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <span class="stock-title">{c['ticker']}</span>
                    <span class="badge badge-sektor">{c['sektor']}</span>
                    <span class="badge badge-fase">Fase Kenaikan: {c['fase']}</span>
                </div>
            </div>
            <div class="metric-row">
                <div class="metric-item">Harga Tembus: <span class="metric-val" style="color:var(--green)">{c['close']:,.0f}</span> (HH20: {c['hh20']:,.0f})</div>
                <div class="metric-item">Vol Ratio (No Supply): <span class="metric-val">{c['vol_ratio']:.2f}x</span></div>
                <div class="metric-item">Value 20H: <span class="metric-val">Rp {c['val_ma20']/1e9:.1f} Miliar</span></div>
                <div class="metric-item">Cut Loss Area (LL20): <span class="metric-val" style="color:var(--red)">{c['ll20']:,.0f}</span></div>
                <div class="metric-item">Kenaikan 120H: <span class="metric-val">+{c['pct_from_bottom_120']:.1f}%</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=False, config={'displayModeBar': False})

    st.subheader(f"🛒 Keranjang 2: Retrace & Compounding ({len(k_retrace)} Saham)")
    st.caption("Aksi: Entry 70% atau Gulung Profit 100%. Syarat: Pernah Breakout, harga tertahan di atas LL20, dan Stochastic Oversold.")
    for c in k_retrace:
        fig = go.Figure(go.Scatter(y=c["price_history"], mode='lines', line=dict(color='#5C8BC6', width=2)))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=50, width=150, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(visible=False))
        
        st.markdown(f"""
        <div class="card-retrace">
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <span class="stock-title">{c['ticker']}</span>
                    <span class="badge badge-sektor">{c['sektor']}</span>
                    <span class="badge badge-fase" style="color:var(--accent-2); border-color:rgba(92,139,198,0.3); background:rgba(92,139,198,0.15)">Fase Kenaikan: {c['fase']}</span>
                </div>
            </div>
            <div class="metric-row">
                <div class="metric-item">Stochastic K: <span class="metric-val" style="color:var(--green)">{c['stoch_k']:.1f} (Oversold)</span></div>
                <div class="metric-item">Harga Tahan: <span class="metric-val">{c['close']:,.0f}</span> (Batas Bawah LL20: <span class="metric-val" style="color:var(--red)">{c['ll20']:,.0f}</span>)</div>
                <div class="metric-item">Vol Ratio (No Supply): <span class="metric-val">{c['vol_ratio']:.2f}x</span></div>
                <div class="metric-item">Value 20H: <span class="metric-val">Rp {c['val_ma20']/1e9:.1f} Miliar</span></div>
                <div class="metric-item">Kenaikan 120H: <span class="metric-val">+{c['pct_from_bottom_120']:.1f}%</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=False, config={'displayModeBar': False})

    st.info("**SOP KEDISIPLINAN (Manual):** Jual Profit 100% jika Stochastic K > 80 selama 2 hari beruntun. Cut Loss seketika jika harga turun 1 tick di bawah Batas Bawah LL20.")
