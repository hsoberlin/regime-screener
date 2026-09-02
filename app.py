"""
TURTLE BOARD
============
Pemindai Donchian 20 hari + kalkulator ukuran Unit (N) untuk Bursa Efek Indonesia.

Aturan asli Turtle System 1 (Dennis & Eckhardt):
    N          = Wilder smoothing 20 hari dari True Range
    1 Unit     = (risiko% x ekuitas) / N, dibulatkan ke bawah per lot
    Masuk      = penutupan menembus tertinggi 20 hari sebelumnya
    Stop Loss  = harga masuk - 2N   (rugi 1 unit = 2 x risiko%)
    Tambah     = tiap naik 0,5N, maksimum 4 unit per saham
    Keluar     = penutupan di bawah terendah 10 hari sebelumnya
    Batas      = 4 per saham, 6 grup berkorelasi, 10 sektor, 12 satu arah
    TIDAK ADA take profit. TIDAK ADA batas waktu tahan. TIDAK ADA skor.

Dua tambahan di luar buku, wajib untuk IDX tanpa margin:
    - saringan likuiditas (transaksi harian TERKECIL 20 hari)
    - batas kas (nilai posisi tidak boleh melebihi kas)

Jalankan:  streamlit run turtle_board.py
Kebutuhan: streamlit yfinance pandas numpy requests
"""

import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

try:
    import requests
    ADA_REQ = True
except Exception:
    ADA_REQ = False

warnings.filterwarnings("ignore")
st.set_page_config(page_title="TURTLE BOARD", layout="wide")

WIB = timezone(timedelta(hours=7))

# =====================================================================
# TAMPILAN
# =====================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@500;800&family=Inter:wght@400;600&display=swap');
.stApp { background-color:#020406; color:#fff; }
.header-container{padding:14px;background:rgba(0,255,204,.02);border-radius:10px;
  border:1px solid rgba(0,255,204,.1);text-align:center;margin-bottom:14px}
.header-title{font-family:'Orbitron',sans-serif!important;font-weight:900;font-size:32px!important;
  background:linear-gradient(90deg,#00ffcc,#3d7fff);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;letter-spacing:5px}
.header-sub{font-family:'JetBrains Mono';font-size:10px;color:#7c8a94;letter-spacing:2px;margin-top:4px}
.macro-strip{display:flex;justify-content:space-around;background:#0a0e14;padding:9px;
  border-radius:5px;border:1px solid #333;margin-bottom:14px;flex-wrap:wrap;gap:6px}
.macro-item{font-family:'JetBrains Mono';font-size:12px;text-align:center;
  padding:6px 10px;border-radius:6px;border:1px solid transparent;min-width:104px}
.macro-up{background:rgba(0,255,204,.09);border-color:rgba(0,255,204,.35)}
.macro-down{background:rgba(255,92,92,.09);border-color:rgba(255,92,92,.35)}
.macro-utama{min-width:150px;padding:6px 14px}
.macro-utama .macro-label{font-size:11px!important;letter-spacing:2px}
.macro-utama .macro-val-up,.macro-utama .macro-val-down{font-size:17px}
/* --- kartu tampilan HP --- */
.kartu{background:#0a0e14;border:1px solid #2a3038;border-radius:8px;
  padding:11px 13px;margin-bottom:9px}
.kartu-segar{border-left:4px solid #00ffcc}
.kartu-ok{border-left:4px solid #3d7fff}
.kartu-tinggal{border-left:4px solid #ffb400}
.kartu-kepala{display:flex;justify-content:space-between;align-items:baseline;
  margin-bottom:7px;flex-wrap:wrap;gap:4px}
.kartu-kode{font-family:'Orbitron';font-size:17px;font-weight:900;color:#fff;letter-spacing:1px}
.kartu-tag{font-family:'JetBrains Mono';font-size:9px;letter-spacing:1px;
  padding:2px 8px;border-radius:10px}
.tag-segar{background:rgba(0,255,204,.15);color:#00ffcc}
.tag-ok{background:rgba(61,127,255,.15);color:#7fa8ff}
.tag-tinggal{background:rgba(255,180,0,.15);color:#ffc94d}
.kartu-baris{font-family:'JetBrains Mono';font-size:11.5px;color:#c3ced6;
  line-height:1.85;border-top:1px solid #1c2229;padding-top:5px}
.kartu-baris b{color:#fff}
.kartu-unit{color:#00ffcc!important;font-weight:800}
.kartu-sl{color:#ff8f8f!important;font-weight:800}
.kartu-wyckoff-siap{border-left:4px solid #c084fc}
.kartu-wyckoff-pantau{border-left:4px solid #7c3aed;opacity:.88}
.kartu-wyckoff-cek{border-left:4px solid #eab308;opacity:.92}
.tag-wyckoff-siap{background:rgba(192,132,247,.18);color:#c084fc}
.tag-wyckoff-pantau{background:rgba(124,58,237,.15);color:#a78bfa}
.tag-wyckoff-cek{background:rgba(234,179,8,.18);color:#facc15}
.macro-label{font-size:9px;color:#888;display:block;margin-bottom:2px;letter-spacing:1px}
.macro-val-up{color:#00ffcc;font-weight:bold}
.macro-val-down{color:#ff6b6b;font-weight:bold}
.kosong{background:rgba(10,14,20,.9);border:1px solid #2a3038;border-radius:8px;
  padding:34px 20px;text-align:center;margin:18px 0}
.kosong-judul{font-family:'Orbitron';font-size:20px;color:#7c8a94;letter-spacing:3px}
.kosong-sub{font-family:'Inter';font-size:12px;color:#5a666e;margin-top:10px;line-height:1.7}
.aturan{background:rgba(2,20,20,.5);border-left:2px solid #00ffcc;padding:11px 14px;
  border-radius:4px;font-family:'Inter';font-size:11.5px;color:#c9d3d8;line-height:1.65}
.aturan b{color:#fff}
.catatan{background:rgba(255,180,0,.05);border-left:2px solid #ffb400;padding:9px 12px;
  border-radius:4px;font-family:'Inter';font-size:11px;color:#c9d3d8;margin-bottom:12px}
[data-testid="stDataFrame"]{border:1px solid #333!important}
[data-testid="stDataFrame"] div[role="columnheader"]{background:#0a0e14!important;color:#00ffcc!important;
  font-family:'Orbitron'!important;font-weight:800!important;border-bottom:1px solid #444!important}
[data-testid="stDataFrame"] div[role="gridcell"]{background:#020406!important;color:#e0e0e0!important;
  font-family:'JetBrains Mono'!important;border-bottom:1px solid #222!important}
section[data-testid="stSidebar"]{background:#060a0f;border-right:1px solid #222}
/* --- keterbacaan: paksa teks terang di seluruh komponen --- */
.stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp div{color:#e8edf0}
/* warna makro TIDAK boleh ditimpa aturan keterbacaan di atas */
.macro-val-up, .stApp .macro-val-up, .stApp div.macro-val-up{color:#00ffcc!important}
.macro-val-down, .stApp .macro-val-down, .stApp div.macro-val-down{color:#ff5c5c!important}
.macro-label, .stApp .macro-label{color:#8b98a3!important}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{color:#9fb0bb!important}
[data-testid="stMarkdownContainer"] p{color:#e8edf0}
.stAlert, .stAlert p{color:#e8edf0!important}
section[data-testid="stSidebar"] *{color:#dfe7ec!important}
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stNumberInput label,
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label{color:#00ffcc!important;font-weight:600}
input, textarea, select{color:#ffffff!important;background:#0d1319!important}
[data-baseweb="select"] div{color:#ffffff!important}
/* --- layar sempit (HP) --- */
@media (max-width:820px){
  .header-title{font-size:22px!important;letter-spacing:2px}
  .header-sub{font-size:8px;letter-spacing:1px}
  .macro-strip{gap:4px;padding:6px}
  .macro-item{font-size:10px;min-width:31%}
  .macro-label{font-size:8px}
  .aturan{font-size:11px;line-height:1.75}
  .catatan{font-size:10.5px}
  .kosong{padding:24px 12px}
  .kosong-judul{font-size:15px;letter-spacing:2px}
  .kosong-sub{font-size:11px}
  .block-container{padding-left:.6rem!important;padding-right:.6rem!important}
}
</style>
""", unsafe_allow_html=True)

# =====================================================================
# PETA GRUP DAN SEKTOR  (untuk batas korelasi, bukan untuk memilih saham)
# =====================================================================
MASTER_AFILIASI = {
    "BREN": "PRAJOGO", "TPIA": "PRAJOGO", "CUAN": "PRAJOGO", "BRPT": "PRAJOGO",
    "PTRO": "PRAJOGO", "CGAS": "PRAJOGO", "CDIA": "PRAJOGO", "GZCO": "PRAJOGO",
    "BUMI": "BAKRIE", "BRMS": "BAKRIE", "ENRG": "BAKRIE", "DEWA": "BAKRIE",
    "BNBR": "BAKRIE", "UNSP": "BAKRIE", "VIVA": "BAKRIE", "MDIA": "BAKRIE",
    "JGLE": "BAKRIE", "ALII": "BAKRIE", "ELTY": "BAKRIE", "BTEL": "BAKRIE", "VKTR": "BAKRIE",
    "AMMN": "SALIM", "INDF": "SALIM", "ICBP": "SALIM", "LSIP": "SALIM", "SIMP": "SALIM",
    "META": "SALIM", "ROTI": "SALIM", "IMAS": "SALIM", "DNET": "SALIM", "MEDC": "SALIM",
    "DSSA": "SINAR MAS", "BSDE": "SINAR MAS", "INKP": "SINAR MAS", "TKIM": "SINAR MAS",
    "SMMA": "SINAR MAS", "DUTI": "SINAR MAS", "SMAR": "SINAR MAS", "FREN": "SINAR MAS",
    "DMAS": "SINAR MAS",
    "PANI": "AGUAN", "MKPI": "AGUAN", "ASRI": "AGUAN", "CBDK": "AGUAN",
    "ADRO": "BOY THOHIR", "ADMR": "BOY THOHIR", "ESSA": "BOY THOHIR",
    "MBMA": "BOY THOHIR", "MDKA": "BOY THOHIR",
    "DRMA": "TP RACHMAT", "TAPG": "TP RACHMAT", "DSNG": "TP RACHMAT",
    "ASSA": "TP RACHMAT", "ASLC": "TP RACHMAT",
    "RAJA": "HAPSORO", "CBRE": "HAPSORO", "PSAB": "HAPSORO", "MINA": "HAPSORO", "OASA": "HAPSORO",
    "JIHD": "TOMY WINATA", "SCBD": "TOMY WINATA", "TINY": "TOMY WINATA",
    "KPIG": "MNC", "BHIT": "MNC", "MNCN": "MNC", "IPTV": "MNC", "BABP": "MNC", "BCAP": "MNC",
    "LPKR": "LIPPO", "LPPF": "LIPPO", "MLPL": "LIPPO", "MPPA": "LIPPO",
    "SILO": "LIPPO", "LPCK": "LIPPO", "MLPT": "LIPPO",
    "GOTO": "TECH", "BUKA": "TECH", "ARTO": "TECH", "EMTK": "EMTEK", "SCMA": "EMTEK",
    "BBRI": "BUMN", "BMRI": "BUMN", "BBNI": "BUMN", "BBTN": "BUMN", "BRIS": "BUMN",
    "TLKM": "BUMN", "ANTM": "BUMN", "PTBA": "BUMN", "TINS": "BUMN", "PGAS": "BUMN",
    "SMGR": "BUMN", "JSMR": "BUMN", "PGEO": "BUMN", "MTEL": "BUMN",
    "WIKA": "BUMN KARYA", "PTPP": "BUMN KARYA", "ADHI": "BUMN KARYA",
    "WTON": "BUMN KARYA", "WEGE": "BUMN KARYA", "PPRE": "BUMN KARYA",
    "ASII": "ASTRA", "UNTR": "ASTRA", "AALI": "ASTRA", "ASGR": "ASTRA", "AUTO": "ASTRA",
    "BBCA": "DJARUM", "TOWR": "DJARUM", "SUPR": "DJARUM",
    "PNBN": "PANIN", "PNIN": "PANIN", "PNLF": "PANIN", "CFIN": "PANIN",
    "AMRT": "ALFAMART", "MIDI": "ALFAMART", "BUDI": "SUNGAI BUDI", "TBLA": "SUNGAI BUDI",
    "MEGA": "CT CORP", "BBHI": "CT CORP",
    "SRTG": "SARATOGA", "TBIG": "SARATOGA", "MPMX": "SARATOGA",
}

SECTOR_MAP = {
    "BBCA": "FINANCE", "BBRI": "FINANCE", "BMRI": "FINANCE", "BBNI": "FINANCE",
    "BBTN": "FINANCE", "BRIS": "FINANCE", "ARTO": "FINANCE", "BJBR": "FINANCE",
    "BJTM": "FINANCE", "TUGU": "FINANCE", "PNBN": "FINANCE", "BDMN": "FINANCE",
    "BBHI": "FINANCE", "SRTG": "FINANCE", "ADMF": "FINANCE", "BNGA": "FINANCE",
    "BNII": "FINANCE", "NISP": "FINANCE",
    "ADRO": "ENERGY", "PTBA": "ENERGY", "ITMG": "ENERGY", "BYAN": "ENERGY",
    "HRUM": "ENERGY", "INDY": "ENERGY", "MEDC": "ENERGY", "ELSA": "ENERGY",
    "PGAS": "ENERGY", "AKRA": "ENERGY", "DOID": "ENERGY", "BUMI": "ENERGY",
    "ENRG": "ENERGY", "RAJA": "ENERGY", "ADMR": "ENERGY", "GEMS": "ENERGY",
    "BSSR": "ENERGY", "PGEO": "ENERGY", "TOBA": "ENERGY",
    "ANTM": "BASIC-MAT", "MDKA": "BASIC-MAT", "INCO": "BASIC-MAT", "TINS": "BASIC-MAT",
    "MBMA": "BASIC-MAT", "NCKL": "BASIC-MAT", "BRMS": "BASIC-MAT", "PSAB": "BASIC-MAT",
    "INKP": "BASIC-MAT", "TKIM": "BASIC-MAT", "SMGR": "BASIC-MAT", "INTP": "BASIC-MAT",
    "TPIA": "BASIC-MAT", "BRPT": "BASIC-MAT", "ESSA": "BASIC-MAT", "LTLS": "BASIC-MAT",
    "AMMN": "BASIC-MAT", "ARCI": "BASIC-MAT", "HRTA": "BASIC-MAT",
    "TLKM": "INFRA", "ISAT": "INFRA", "EXCL": "INFRA", "FREN": "INFRA", "JSMR": "INFRA",
    "TBIG": "INFRA", "TOWR": "INFRA", "MTEL": "INFRA", "META": "INFRA", "PPRE": "INFRA",
    "ADHI": "INFRA", "WIKA": "INFRA", "PTPP": "INFRA",
    "ICBP": "CONSUMER", "INDF": "CONSUMER", "UNVR": "CONSUMER", "MYOR": "CONSUMER",
    "AMRT": "CONSUMER", "MIDI": "CONSUMER", "ACES": "CONSUMER", "MAPI": "CONSUMER",
    "MAPA": "CONSUMER", "CPIN": "CONSUMER", "JPFA": "CONSUMER", "GGRM": "CONSUMER",
    "HMSP": "CONSUMER", "KLBF": "CONSUMER", "SIDO": "CONSUMER", "AUTO": "CONSUMER",
    "ASII": "CONSUMER", "ERAA": "CONSUMER",
    "BSDE": "PROPERTY", "CTRA": "PROPERTY", "SMRA": "PROPERTY", "PWON": "PROPERTY",
    "ASRI": "PROPERTY", "DILD": "PROPERTY", "PANI": "PROPERTY", "APLN": "PROPERTY",
    "LPCK": "PROPERTY", "LPKR": "PROPERTY", "BEST": "PROPERTY", "DMAS": "PROPERTY",
    "GOTO": "TECH", "BUKA": "TECH", "EMTK": "TECH", "SCMA": "TECH", "WIRG": "TECH",
    "DCII": "TECH", "MTDL": "TECH",
    "ASSA": "TRANS", "BIRD": "TRANS", "SMDR": "TRANS", "TMAS": "TRANS",
    "GIAA": "TRANS", "IATA": "TRANS",
    "AALI": "PLANTATION", "LSIP": "PLANTATION", "SIMP": "PLANTATION", "SMAR": "PLANTATION",
    "DSNG": "PLANTATION", "TAPG": "PLANTATION", "SGRO": "PLANTATION",
    "UNTR": "HEAVY-EQP", "PTRO": "HEAVY-EQP",
}

FALLBACK_UNIVERSE = sorted(set(list(MASTER_AFILIASI) + list(SECTOR_MAP)))

# =====================================================================
# PENGAMBILAN DATA
# =====================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def ambil_universe():
    """Daftar emiten IDX dari screener TradingView. Gagal -> daftar bawaan."""
    if not ADA_REQ:
        return FALLBACK_UNIVERSE, "bawaan", {}, {}, {}
    try:
        body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"}],
                "columns": ["name", "sector", "market_cap_basic",
                            "float_shares_percent_current"], "range": [0, 1200],
                "sort": {"sortBy": "name", "sortOrder": "asc"}}
        r = requests.post("https://scanner.tradingview.com/indonesia/scan",
                          json=body, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        rows = r.json().get("data", [])
        tics, sect, mcap, ff = [], {}, {}, {}
        for d in rows:
            kode = d["d"][0]
            if kode and kode.isalpha() and 3 <= len(kode) <= 5:
                tics.append(kode)
                if d["d"][1]:
                    sect.setdefault(kode, d["d"][1])
                if d["d"][2]:
                    mcap[kode] = float(d["d"][2])
                if len(d["d"]) > 3 and d["d"][3]:
                    ff[kode] = float(d["d"][3])
        if len(tics) > 200:
            for k, v in sect.items():
                SECTOR_MAP.setdefault(k, v)
            return sorted(set(tics)), "TradingView", mcap, ff
    except Exception:
        pass
    return FALLBACK_UNIVERSE, "bawaan", {}, {}


@st.cache_data(ttl=900, show_spinner=False)
def ambil_harga(tickers, periode="1y", batch=80):
    """Unduh bar harian secara batch."""
    keluar = {}
    for i in range(0, len(tickers), batch):
        chunk = [f"{t}.JK" for t in tickers[i:i + batch]]
        try:
            df = yf.download(chunk, period=periode, interval="1d", progress=False,
                             auto_adjust=False, group_by="ticker", threads=True)
        except Exception:
            continue
        for sym in chunk:
            kode = sym[:-3]
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(sub) >= 60:
                    keluar[kode] = sub
            except Exception:
                continue
    return keluar


@st.cache_data(ttl=900, show_spinner=False)
def ambil_makro():
    out = {}
    peta = {"^JKSE": "IHSG", "IDR=X": "USDIDR", "CL=F": "MINYAK",
            "GC=F": "EMAS", "HG=F": "TEMBAGA", "^IXIC": "NASDAQ"}
    try:
        df = yf.download(list(peta), period="1mo", interval="1d", progress=False,
                         auto_adjust=False, group_by="ticker", threads=True)
        for sym, nama in peta.items():
            try:
                s = (df[sym]["Close"] if isinstance(df.columns, pd.MultiIndex)
                     else df["Close"]).dropna()
                if len(s) >= 2:
                    out[nama] = {"val": float(s.iloc[-1]),
                                 "chg": float(s.iloc[-1] / s.iloc[-2] - 1) * 100}
            except Exception:
                continue
    except Exception:
        pass
    return out


# =====================================================================
# MESIN TURTLE
# =====================================================================
def hitung_N(df, periode=20):
    """N = Wilder smoothing 20 hari dari True Range. Rumus asli Turtle."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (pc - l).abs()], axis=1).max(axis=1)
    seed = tr.rolling(periode).mean()
    v = np.array(seed.values, dtype=float, copy=True)
    t = np.array(tr.values, dtype=float, copy=True)
    for i in range(periode + 1, len(v)):
        if not np.isnan(v[i - 1]):
            v[i] = (v[i - 1] * (periode - 1) + t[i]) / periode
    return v[-1]


def metrik(kode, df, p_masuk, p_keluar):
    if len(df) < p_masuk + 25:
        return None
    C = df["Close"].values.astype(float)
    V = df["Volume"].values.astype(float)
    n = hitung_N(df, 20)
    if not np.isfinite(n) or n <= 0:
        return None
    seri_tinggi = df["High"].shift(1).rolling(p_masuk).max()
    tinggi = float(seri_tinggi.iloc[-1])
    rendah = float(df["Low"].shift(1).rolling(p_keluar).min().iloc[-1])

    # berapa hari sejak tembus PERTAMA dalam rentetan yang sedang berjalan,
    # dan berapa jauh harga sudah lari sejak hari itu
    tembus_seri = (df["Close"] > seri_tinggi).values
    hari_sejak, lari = np.nan, np.nan
    if len(tembus_seri) and bool(tembus_seri[-1]):
        i = len(tembus_seri) - 1
        while i > 0 and tembus_seri[i]:
            i -= 1
        awal = i + 1
        hari_sejak = float(len(tembus_seri) - 1 - awal)
        if C[awal] > 0:
            lari = float(C[-1] / C[awal] - 1)
    volrata = float(np.mean(V[-21:-1])) or 1.0
    tv = (C * V)[-20:]
    return dict(
        kode=kode, harga=float(C[-1]), N=float(n),
        tinggi20=tinggi, rendah10=rendah,
        vol_rasio=float(V[-1] / volrata),
        rp1pct=rupiah_per_1persen(df),
        turn_min20=float(np.min(tv)), turn_med=float(np.median(tv)),
        turn_med_m=float(np.median(tv)) / 1e9,
        tembus=bool(C[-1] > tinggi),
        hari_sejak=hari_sejak, lari=lari,
        jarak=float(C[-1] / tinggi - 1) if tinggi else np.nan,
        grup=MASTER_AFILIASI.get(kode, "-"),
        sektor=SECTOR_MAP.get(kode, "-"),
        tanggal=df.index[-1].strftime("%d %b %Y"),
    )


def metrik_wyckoff(df, jendela=150, jendela_range=15):
    """Prefilter re-akumulasi ala Wyckoff. Bukan sinyal masuk — cuma penyaring kandidat.

    Jendela 150 hari (~7 bulan) — bukan 50 hari — supaya rally besar sebelum topping yang
    genuinely butuh berbulan-bulan ikut tertangkap. Rally & turun dicari di window yang sama.

    Lima syarat (dicek di luar fungsi ini, di baris DataFrame):
        rally     : tertinggi jendela >= harga awal jendela x (1 + rally_min)
        turun     : harga sekarang <= tertinggi jendela x (1 - turun_min)
        sideways  : puncak terjadi >= sideways_min_hari yang lalu (bukan baru topping)
        range     : lebar high-low 15 hari terakhir <= range_maks
        volume    : rata-rata volume 20 hari >= rata-rata 50 hari x volume_mult
    """
    if len(df) < jendela + 5:
        return None
    sub = df.tail(jendela)
    H = sub["High"].values.astype(float)
    C = sub["Close"].values.astype(float)

    tertinggi_puncak = float(H.max())
    idx_puncak = int(np.argmax(H))
    harga_awal = float(C[0])
    harga_now = float(C[-1])
    hari_sejak_puncak = (jendela - 1) - idx_puncak

    rally_pct = (tertinggi_puncak / harga_awal - 1) if harga_awal > 0 else np.nan
    turun_pct = (harga_now / tertinggi_puncak - 1) if tertinggi_puncak > 0 else np.nan

    sub15 = df.tail(jendela_range)
    low15min = float(sub15["Low"].min())
    range15_pct = ((float(sub15["High"].max()) - low15min) / low15min) if low15min > 0 else np.nan

    vol = df["Volume"]
    volma20 = float(vol.tail(20).mean())
    volma50 = float(vol.tail(50).mean())
    vol_rasio_ma = (volma20 / volma50) if volma50 > 0 else np.nan

    return dict(
        tertinggi_puncak=tertinggi_puncak, rally_pct=rally_pct, turun_pct=turun_pct,
        hari_sejak_puncak=float(hari_sejak_puncak), range15_pct=range15_pct,
        vol_rasio_ma=vol_rasio_ma,
    )


BOBOT_BATAS = [(200e9, "SANGAT TEBAL"), (50e9, "TEBAL"), (10e9, "SEDANG"), (0, "TIPIS")]
BOBOT_PILIHAN = ["TIPIS", "SEDANG", "TEBAL", "SANGAT TEBAL", "?"]


def rupiah_per_1persen(df, jendela=60, min_nilai=1e6):
    """Amihud: berapa rupiah transaksi dibutuhkan untuk menggerakkan harga 1%.

    Median dipakai, bukan rata-rata — rata-rata terseret hari-hari sepi.
    Jendela 60 hari supaya mencerminkan keadaan sekarang, bukan setahun lalu.
    """
    sub = df.tail(jendela)
    C = sub["Close"]
    nilai = C * sub["Volume"]
    ret = C.pct_change().abs()
    m = (nilai > min_nilai) & ret.notna() & (ret > 0)
    if int(m.sum()) < 25:
        return np.nan
    rasio = float((ret[m] / nilai[m]).median())
    return 0.01 / rasio if rasio > 0 else np.nan


def label_bobot(v):
    """Ukuran Amihud — perbandingan ketebalan antar saham.

    PENTING: ini BUKAN biaya untuk menggerakkan harga. Angkanya median dari
    hubungan gerak-harga dengan nilai transaksi, dan sebarannya lebar (AADI
    berkisar 30-200 M dalam 60 hari yang sama). Lompatan pembukaan tidak
    terukur sama sekali. Pakai untuk membandingkan saham, bukan sebagai
    angka mutlak.
    """
    if v is None or not np.isfinite(v) or v <= 0:
        return "?"
    for batas, nama in BOBOT_BATAS:
        if v >= batas:
            return nama
    return "TIPIS"


def ukuran_unit(ekuitas, N, risiko):
    """1 Unit = (risiko% x ekuitas) / N, dibulatkan ke bawah per lot."""
    if N <= 0 or ekuitas <= 0:
        return 0
    return int(((ekuitas * risiko) / N) // 100)


# =====================================================================
# SIDEBAR
# =====================================================================
st.sidebar.markdown("### EKUITAS")
mode_rekam = st.sidebar.toggle(
    "Mode rekam", value=False,
    help="Untuk perekaman layar: ekuitas dan kas diganti angka contoh yang bulat. "
         "Seluruh hitungan tetap benar, cuma modalnya bukan modalmu.")

if mode_rekam:
    ekuitas = st.sidebar.number_input("Ekuitas contoh (Rp)", 0, 10_000_000_000,
                                      100_000_000, 10_000_000)
    kas = st.sidebar.number_input("Kas contoh (Rp)", 0, 10_000_000_000,
                                  50_000_000, 10_000_000)
    st.sidebar.caption("Mode rekam menyala — angka di layar bukan modal sebenarnya.")
else:
    ekuitas = st.sidebar.number_input(
        "Ekuitas (Rp)", min_value=0, max_value=10_000_000_000,
        value=58_233_835, step=100_000,
        help="Dipakai untuk menghitung ukuran Unit. Perbarui setiap ada transaksi match.")
    kas = st.sidebar.number_input(
        "Kas bebas (Rp)", min_value=0, max_value=10_000_000_000,
        value=28_773_603, step=100_000,
        help="Batas keras: nilai 1 unit tidak boleh melebihi kas.")

st.sidebar.markdown("### ATURAN TURTLE")
risiko = st.sidebar.select_slider("Risiko per Unit (% ekuitas)",
                                  options=[0.5, 0.75, 1.0, 1.25, 1.5], value=1.0) / 100
p_masuk = st.sidebar.number_input("Periode tembus (masuk)", 5, 60, 20)
p_keluar = st.sidebar.number_input("Periode keluar", 3, 30, 10)
maks_unit = st.sidebar.number_input("Maks unit per saham", 1, 12, 4)

st.sidebar.markdown("### EKUITAS SPRING (akun FUNDAMENTAL)")
st.sidebar.caption("Terpisah dari ekuitas OBERLIN di atas. Dipakai khusus tab WYCKOFF SPRING.")
if mode_rekam:
    ekuitas_spring = st.sidebar.number_input("Ekuitas SPRING contoh (Rp)", 0, 10_000_000_000,
                                             9_500_000, 500_000)
    kas_spring = st.sidebar.number_input("Kas SPRING contoh (Rp)", 0, 10_000_000_000,
                                         9_500_000, 500_000)
else:
    ekuitas_spring = st.sidebar.number_input(
        "Ekuitas SPRING (Rp)", min_value=0, max_value=10_000_000_000,
        value=9_518_963, step=100_000,
        help="Modal gabungan sisa kas OBERLIN + FUNDAMENTAL + TEKNIKAL yang dialokasikan ke SPRING.")
    kas_spring = st.sidebar.number_input(
        "Kas bebas SPRING (Rp)", min_value=0, max_value=10_000_000_000,
        value=9_518_963, step=100_000,
        help="Batas keras: nilai 1 unit SPRING tidak boleh melebihi ini.")

st.sidebar.markdown("### ATURAN WYCKOFF SPRING")
st.sidebar.caption("Prefilter re-akumulasi, dipakai bareng semesta yang sama dengan Turtle Board. "
                   "Bukan sinyal masuk — cuma penyaring kandidat sebelum dicek Turtle.")
rally_min = st.sidebar.slider("Rally minimal sebelum puncak (%)", 20, 150, 50, 5) / 100
turun_min = st.sidebar.slider("Turun minimal dari puncak (%)", 5, 50, 20, 5) / 100
sideways_min_hari = st.sidebar.number_input("Sideways minimal (hari)", 5, 60, 15, 1)
range_maks = st.sidebar.slider("Lebar range 15 hari maksimal (%)", 5, 50, 20, 5) / 100
volume_mult = st.sidebar.slider("Volume MA20 vs MA50 (kelipatan)", 1.0, 3.0, 1.2, 0.1)

st.sidebar.markdown("### SARINGAN IDX")
st.sidebar.caption("Dua saringan di bawah TIDAK ada di aturan Turtle. Wajib untuk IDX tanpa margin.")
amb_likuid = st.sidebar.selectbox(
    "Transaksi harian minimal", [0, 1e9, 2e9, 5e9, 1e10],
    index=3, format_func=lambda v: "Tanpa batas" if v == 0 else f"Rp {v/1e9:.0f} miliar")
harga_min = st.sidebar.number_input("Harga minimal", 0, 100000, 50, 50)
bobot_dipakai = st.sidebar.multiselect(
    "Ketebalan pasar", BOBOT_PILIHAN, default=BOBOT_PILIHAN,
    help="Perbandingan antar saham, bukan angka mutlak. TIPIS = harga bergerak jauh dengan "
         "transaksi sedikit, dua arah. Uji 2 tahun tidak menemukan pola yang bisa diandalkan "
         "antara ketebalan dan hasil, jadi pakai sebagai konteks saja.")

st.sidebar.markdown("### DAFTAR MENDEKATI TEMBUS")
ambang_dekat = st.sidebar.slider("Jarak maksimal dari level tembus (%)", 1.0, 15.0, 5.0, 0.5,
                                 help="Peluang tembus besok: jarak 1% = 25%, 2% = 16%, "
                                      "3% = 11%, 5% = 7%, 8% = 4%.")
maks_kartu = st.sidebar.number_input("Maksimal kartu ditampilkan (0 = semua)", 0, 200, 0, 5)

st.sidebar.markdown("### TAMPILAN")
mode_tampil = st.sidebar.radio("Bentuk hasil", ["Tabel (layar lebar)", "Kartu (HP)"], index=0,
                               help="Kartu: semua angka muat dalam satu tangkapan layar tegak.")

st.sidebar.markdown("### SEMESTA")
mode_universe = st.sidebar.radio("Cakupan", ["Semua IDX", "Grup terpantau saja"], index=0,
                                 help="Semua IDX: putaran pertama 2-4 menit, lalu di-cache 15 menit.")

# =====================================================================
# HALAMAN
# =====================================================================
st.markdown('<div class="header-container"><div class="header-title">TURTLE BOARD</div>'
            '<div class="header-sub">DONCHIAN 20 HARI &nbsp;·&nbsp; UKURAN UNIT BERBASIS N '
            '&nbsp;·&nbsp; STOP 2N &nbsp;·&nbsp; KELUAR 10 HARI</div></div>',
            unsafe_allow_html=True)

makro = ambil_makro()
if makro:
    urut = ["IHSG"] + [k for k in makro if k != "IHSG"]
    html = "<div class='macro-strip'>"
    for k in urut:
        v = makro.get(k)
        if not v:
            continue
        naik = v["chg"] >= 0
        cls_teks = "macro-val-up" if naik else "macro-val-down"
        cls_kotak = "macro-up" if naik else "macro-down"
        utama = " macro-utama" if k == "IHSG" else ""
        panah = "&#9650;" if naik else "&#9660;"
        html += (f"<div class='macro-item {cls_kotak}{utama}'>"
                 f"<span class='macro-label'>{k}</span>"
                 f"<span class='{cls_teks}'>{v['val']:,.2f} {panah} {abs(v['chg']):.2f}%</span></div>")
    st.markdown(html + "</div>", unsafe_allow_html=True)

st.markdown(f"""<div class="aturan">
{'<b>MODE REKAM</b> &nbsp;·&nbsp; angka di bawah adalah contoh, bukan modal sebenarnya<br>' if mode_rekam else ''}
<b>Risiko 1 unit:</b> Rp {ekuitas*risiko*2:,.0f} &nbsp;(= 2N x {risiko*100:.2f}% ekuitas)
&nbsp;·&nbsp; <b>Kas bebas:</b> Rp {kas:,.0f}
&nbsp;·&nbsp; <b>Batas:</b> {maks_unit} unit/saham · 6 unit/grup · 10 unit/sektor · 12 unit total<br>
Tidak ada take profit. Tidak ada target. Tidak ada skor. Keluar hanya lewat terendah
{p_keluar} hari atau stop 2N.
</div>""".replace(",", "."), unsafe_allow_html=True)

if "hasil" not in st.session_state:
    st.session_state.hasil = None
    st.session_state.info = None

if st.button("PINDAI SEMESTA IDX", type="primary", use_container_width=True):
    with st.spinner("Menarik daftar emiten..."):
        universe, sumber, mcap, ff = ambil_universe()
    if mode_universe == "Grup terpantau saja":
        universe = sorted(set(FALLBACK_UNIVERSE) & set(universe)) or FALLBACK_UNIVERSE
    with st.spinner(f"Menarik bar harian {len(universe)} emiten (putaran pertama 2-4 menit)..."):
        harga = ambil_harga(tuple(universe))

    baris = []
    for kode, df in harga.items():
        try:
            m = metrik(kode, df, int(p_masuk), int(p_keluar))
            if m:
                w = metrik_wyckoff(df)
                m.update(w if w else dict(
                    tertinggi_puncak=np.nan, rally_pct=np.nan, turun_pct=np.nan,
                    hari_sejak_puncak=np.nan, range15_pct=np.nan, vol_rasio_ma=np.nan))
                baris.append(m)
        except Exception:
            continue

    d = pd.DataFrame(baris)
    if not d.empty:
        d["mcap"] = d["kode"].map(mcap).fillna(0)
        d["ff"] = d["kode"].map(ff)
        d["bobot"] = d["rp1pct"].apply(label_bobot)
        d["rp1pct_m"] = d["rp1pct"] / 1e9
        d = d[(d["turn_min20"] >= amb_likuid) & (d["harga"] >= harga_min)]
        d["unit_lot"] = d["N"].apply(lambda n: ukuran_unit(ekuitas, n, risiko))
        d["nilai_unit"] = d["unit_lot"] * 100 * d["harga"]
        d["sl_2n"] = d["harga"] - 2 * d["N"]
        d["rugi_unit"] = d["unit_lot"] * 100 * 2 * d["N"]
        d["pct_kas"] = d["nilai_unit"] / kas * 100 if kas else np.nan
        d["muat"] = np.where(d["nilai_unit"] <= kas, "YA", "TIDAK")
        d["kesegaran"] = np.where(
            ~d["tembus"], "-",
            np.where(d["hari_sejak"].fillna(99) == 0, "SEGAR",
            np.where((d["hari_sejak"].fillna(99) <= 2) & (d["lari"].fillna(9) < 0.05),
                     "MASIH OK", "TERTINGGAL")))

        # --- Wyckoff SPRING: flag kelolosan per syarat (NaN dianggap gagal) ---
        d["rally_ok"] = d["rally_pct"].fillna(-999) >= rally_min
        d["turun_ok"] = d["turun_pct"].fillna(999) <= -turun_min
        d["sideways_ok"] = d["hari_sejak_puncak"].fillna(-999) >= sideways_min_hari
        d["range_ok"] = d["range15_pct"].fillna(999) <= range_maks
        d["volume_ok"] = d["vol_rasio_ma"].fillna(-999) >= volume_mult

        # empat syarat dasar (struktur harga) wajib semua; volume MENENTUKAN TIER, bukan gerbang tunggal
        dasar_ok = d["rally_ok"] & d["turun_ok"] & d["sideways_ok"] & d["range_ok"]
        d["tier_siap"] = dasar_ok & d["volume_ok"]          # absorption klasik: volume ramai
        d["tier_cek_broker"] = dasar_ok & (~d["volume_ok"])  # quiet accumulation: volume sepi, cek broker flow manual
        d["lolos_wyckoff"] = dasar_ok  # dipakai kalau perlu gabungan kedua tier

        # --- Wyckoff SPRING: ukuran unit pakai ekuitas/kas SPRING, terpisah dari OBERLIN ---
        d["unit_lot_spring"] = d["N"].apply(lambda n: ukuran_unit(ekuitas_spring, n, risiko))
        d["nilai_unit_spring"] = d["unit_lot_spring"] * 100 * d["harga"]
        d["rugi_unit_spring"] = d["unit_lot_spring"] * 100 * 2 * d["N"]
        d["pct_kas_spring"] = d["nilai_unit_spring"] / kas_spring * 100 if kas_spring else np.nan
        d["muat_spring"] = np.where(d["nilai_unit_spring"] <= kas_spring, "YA", "TIDAK")
    st.session_state.hasil = d
    st.session_state.info = (sumber, len(harga), len(d) if not d.empty else 0)

d = st.session_state.hasil

if d is None:
    st.markdown('<div class="kosong"><div class="kosong-judul">BELUM DIPINDAI</div>'
                '<div class="kosong-sub">Tekan tombol di atas untuk memindai bursa.</div></div>',
                unsafe_allow_html=True)
    st.stop()

if d.empty:
    st.markdown('<div class="kosong"><div class="kosong-judul">TIDAK ADA DATA</div>'
                '<div class="kosong-sub">Saringan likuiditas mungkin terlalu ketat.</div></div>',
                unsafe_allow_html=True)
    st.stop()

sumber, n_hitung, n_lolos = st.session_state.info
st.markdown(f"<div style='text-align:center;color:#5a666e;font-family:JetBrains Mono;"
            f"font-size:10px;letter-spacing:2px;margin-bottom:12px'>"
            f"{n_hitung} EMITEN DIHITUNG ({sumber}) &nbsp;·&nbsp; {n_lolos} LOLOS SARINGAN "
            f"&nbsp;·&nbsp; DATA {d['tanggal'].iloc[0]} &nbsp;·&nbsp; "
            f"{datetime.now(WIB).strftime('%d %b %Y %H:%M WIB')}</div>",
            unsafe_allow_html=True)

KOLOM = {"kode": "KODE", "kesegaran": "KESEGARAN", "hari_sejak": "TEMBUS",
         "lari": "LARI SEJAK", "harga": "HARGA", "N": "N",
         "tinggi20": f"TERTINGGI {p_masuk}H", "jarak": "JARAK", "vol_rasio": "VOL",
         "unit_lot": "1 UNIT", "nilai_unit": "NILAI UNIT", "sl_2n": "SL 2N",
         "rugi_unit": "RUGI 1 UNIT", "pct_kas": "% KAS",
         "rendah10": f"KELUAR {p_keluar}H", "muat": "MUAT KAS",
         "turn_med_m": "TRANSAKSI/HARI", "ff": "FF%", "bobot": "TEBAL",
         "grup": "GRUP", "sektor": "SEKTOR"}
URUT = list(KOLOM)

KONF = {
    "KESEGARAN": st.column_config.TextColumn(
        help="SEGAR = tembus hari ini. TERTINGGAL = sudah lari jauh sejak tembus."),
    "TEMBUS": st.column_config.TextColumn(help="Berapa hari lalu menembus tertinggi 20 hari"),
    "LARI SEJAK": st.column_config.NumberColumn(
        format="%.1f%%", help="Kenaikan harga sejak hari tembus. Makin besar, makin buruk entry-mu."),
    "TRANSAKSI/HARI": st.column_config.NumberColumn(
        format="%.2f M", help="Nilai transaksi harian, median 20 hari, dalam miliar rupiah."),
    "FF%": st.column_config.NumberColumn(
        format="%.0f%%", help="Persentase saham beredar bebas. Makin kecil, makin sedikit "
                              "barang yang benar-benar bisa diperdagangkan."),
    "TEBAL": st.column_config.TextColumn(
        help="Ukuran Amihud: TIPIS < 10 M · SEDANG 10-50 M · TEBAL 50-200 M · "
             "SANGAT TEBAL > 200 M. Ini perbandingan antar saham, BUKAN biaya yang "
             "dibutuhkan untuk menggerakkan harga."),
    "HARGA": st.column_config.NumberColumn(format="%.0f"),
    "N": st.column_config.NumberColumn(format="%.2f", help="Rata-rata gerak harian 20 hari"),
    "JARAK": st.column_config.NumberColumn(format="%.2f%%", help="Jarak harga ke level tembus"),
    "VOL": st.column_config.NumberColumn(format="%.2fx", help="Volume hari ini / rata-rata 20 hari"),
    "1 UNIT": st.column_config.NumberColumn(format="%d lot"),
    "NILAI UNIT": st.column_config.NumberColumn(format="%.0f"),
    "SL 2N": st.column_config.NumberColumn(format="%.1f"),
    "RUGI 1 UNIT": st.column_config.NumberColumn(format="%.0f"),
    "% KAS": st.column_config.NumberColumn(format="%.1f%%"),
}


def tampil(sub):
    t = sub[URUT].rename(columns=KOLOM).copy()
    t["JARAK"] = t["JARAK"] * 100
    t["LARI SEJAK"] = t["LARI SEJAK"] * 100
    t["TEMBUS"] = t["TEMBUS"].apply(
        lambda v: "-" if pd.isna(v) else ("hari ini" if v == 0 else f"{int(v)} hari lalu"))
    return t


def tampil_ringkas(sub):
    """Tabel untuk daftar yang belum tembus: tiga kolom kesegaran dilepas."""
    t = tampil(sub)
    return t.drop(columns=["KESEGARAN", "TEMBUS", "LARI SEJAK"])


def kartu(sub, kas_bebas):
    """Satu blok per saham — muat dalam satu tangkapan layar HP."""
    gaya = {"SEGAR": ("kartu-segar", "tag-segar"),
            "MASIH OK": ("kartu-ok", "tag-ok"),
            "TERTINGGAL": ("kartu-tinggal", "tag-tinggal"),
            "-": ("", "tag-ok")}
    rp = lambda v: f"{v:,.0f}".replace(",", ".")
    blok = []
    for _, r in sub.iterrows():
        kb, kt = gaya.get(r["kesegaran"], ("", "tag-ok"))
        if pd.isna(r["hari_sejak"]):
            kapan = "belum tembus"
        elif r["hari_sejak"] == 0:
            kapan = "tembus hari ini"
        else:
            kapan = f"tembus {int(r['hari_sejak'])} hari lalu &middot; lari +{r['lari']*100:.1f}%"
        muat = ("" if r["muat"] == "YA"
                else " <span style='color:#ff8f8f'>&middot; TIDAK MUAT KAS</span>")
        blok.append(f"""<div class="kartu {kb}">
  <div class="kartu-kepala">
    <span class="kartu-kode">{r['kode']}</span>
    <span class="kartu-tag {kt}">{'' if r['kesegaran'] == '-' else r['kesegaran']} &nbsp;{kapan}</span>
  </div>
  <div class="kartu-baris">
    Harga <b>{rp(r['harga'])}</b> &middot; N <b>{r['N']:.2f}</b> &middot;
    tertinggi20 <b>{rp(r['tinggi20'])}</b> ({r['jarak']*100:+.2f}%) &middot;
    vol <b>{r['vol_rasio']:.2f}x</b><br>
    <span class="kartu-unit">1 unit {int(r['unit_lot'])} lot = Rp{rp(r['nilai_unit'])}</span>
    ({r['pct_kas']:.1f}% kas){muat}<br>
    <span class="kartu-sl">SL 2N {r['sl_2n']:.1f}</span> &middot;
    rugi 1 unit <b>Rp{rp(r['rugi_unit'])}</b> &middot;
    keluar10H <b>{rp(r['rendah10'])}</b><br>
    Transaksi/hari <b>Rp{r.get('turn_med_m', 0):.2f} M</b> &middot;
    free float <b>{f"{r['ff']:.0f}%" if r.get('ff') else '-'}</b> &middot;
    <b>{r.get('bobot', '?')}</b><br>
    <span style="color:#7c8a94">{r['grup']} &middot; {r['sektor']}</span>
  </div>
</div>""")
    return "".join(blok)


def kartu_wyckoff(sub, status):
    """Kartu watchlist SPRING.

    status: "siap_tembus" | "siap_pantau" | "cek_broker"
        siap_*      -> tier SIAP (5/5 syarat termasuk volume tinggi, absorption klasik)
        cek_broker  -> tier volume sepi (4/5 syarat, quiet accumulation) -- wajib cek
                       gauge Broker Action (Big Dist <-> Big Acc) di Stockbit manual
                       sebelum dianggap kandidat, berapa pun status tembusnya.
    """
    rp = lambda v: f"{v:,.0f}".replace(",", ".")
    gaya = {
        "siap_tembus": ("kartu-wyckoff-siap", "tag-wyckoff-siap", "SUDAH TEMBUS"),
        "siap_pantau": ("kartu-wyckoff-siap", "tag-wyckoff-siap", "BELUM TEMBUS"),
        "cek_broker": ("kartu-wyckoff-cek", "tag-wyckoff-cek", "CEK BROKER FLOW"),
    }
    kelas, tag, label_dasar = gaya[status]
    blok = []
    for _, r in sub.iterrows():
        muat = ("" if r["muat_spring"] == "YA"
                else " <span style='color:#ff8f8f'>&middot; TIDAK MUAT KAS SPRING</span>")
        if status == "siap_tembus":
            status_teks = "TEMBUS HARI INI" if r.get("hari_sejak") == 0 else label_dasar
        elif status == "cek_broker":
            tembus_teks = "sudah tembus" if r.get("tembus") else "belum tembus"
            status_teks = f"{label_dasar} &middot; {tembus_teks}"
        else:
            status_teks = label_dasar
        blok.append(f"""<div class="kartu {kelas}">
  <div class="kartu-kepala">
    <span class="kartu-kode">{r['kode']}</span>
    <span class="kartu-tag {tag}">{status_teks}</span>
  </div>
  <div class="kartu-baris">
    Harga <b>{rp(r['harga'])}</b> &middot; puncak150 <b>{rp(r['tertinggi_puncak'])}</b>
    (rally +{r['rally_pct']*100:.0f}% &middot; turun {r['turun_pct']*100:.0f}%)<br>
    Sideways <b>{int(r['hari_sejak_puncak'])} hari</b> &middot;
    range15H <b>{r['range15_pct']*100:.1f}%</b> &middot;
    volMA20/50 <b>{r['vol_rasio_ma']:.2f}x</b><br>
    <span class="kartu-unit">Masuk (tertinggi20) <b>{rp(r['tinggi20'])}</b></span> &middot;
    <span class="kartu-sl">keluar (terendah10) <b>{rp(r['rendah10'])}</b></span><br>
    N <b>{r['N']:.2f}</b> &middot; SL 2N <b>{r['sl_2n']:.1f}</b> &middot;
    <span class="kartu-unit">usulan (referensi) {int(r['unit_lot_spring'])} lot = Rp{rp(r['nilai_unit_spring'])}</span>
    ({r['pct_kas_spring']:.1f}% kas){muat}<br>
    <span style="color:#7c8a94">Sizing aktual sesuai insting — catat lot rekomendasi vs lot aktual di jurnal</span><br>
    <span style="color:#7c8a94">{r['grup']} &middot; {r['sektor']}</span>
  </div>
</div>""")
    return "".join(blok)


urut_segar = {"SEGAR": 0, "MASIH OK": 1, "TERTINGGAL": 2}
if "bobot" in d.columns and bobot_dipakai:
    d = d[d["bobot"].isin(bobot_dipakai)]
    if d.empty:
        st.warning("Tidak ada saham yang cocok dengan bobot pasar yang dipilih.")
        st.stop()

tab1, tab2 = st.tabs(["🐢 TURTLE BOARD", "🌀 WYCKOFF SPRING"])

with tab1:
    sinyal = d[d["tembus"]].copy()
    if not sinyal.empty:
        sinyal["_u"] = sinyal["kesegaran"].map(urut_segar).fillna(3)
        sinyal = sinyal.sort_values(["_u", "lari"], ascending=[True, True])
    dekat = d[(~d["tembus"]) & (d["jarak"] >= -ambang_dekat / 100)].sort_values("jarak", ascending=False)

    st.markdown(f"<h3 style='font-family:Orbitron;color:#00ffcc;font-size:16px;letter-spacing:2px'>"
                f"SINYAL MASUK &nbsp;—&nbsp; {len(sinyal)} SAHAM</h3>", unsafe_allow_html=True)

    if sinyal.empty:
        st.markdown(f'<div class="kosong"><div class="kosong-judul">TIDAK ADA SINYAL</div>'
                    f'<div class="kosong-sub">Tidak ada saham yang menembus tertinggi {p_masuk} hari '
                    f'hari ini.<br>Ini keadaan normal — sebagian besar hari memang begitu.<br>'
                    f'Catat tanggal ini di jurnal dengan keterangan "tidak ada sinyal".</div></div>',
                    unsafe_allow_html=True)
    else:
        if mode_tampil.startswith("Kartu"):
            st.markdown(kartu(sinyal, kas), unsafe_allow_html=True)
        else:
            st.dataframe(tampil(sinyal), use_container_width=True, hide_index=True,
                         column_config=KONF, height=min(60 + 35 * len(sinyal), 420))
        muat = sinyal[sinyal["muat"] == "YA"]
        n_segar = int((sinyal["kesegaran"] == "SEGAR").sum())
        n_tinggal = int((sinyal["kesegaran"] == "TERTINGGAL").sum())
        st.caption(f"{len(muat)} dari {len(sinyal)} muat di kas Rp{kas:,.0f}".replace(",", ".") +
                   f" · {n_segar} tembus hari ini · {n_tinggal} sudah tertinggal.")
        if n_tinggal:
            st.markdown(
                f"""<div class="catatan"><b>{n_tinggal} saham berlabel TERTINGGAL.</b>
    Mereka menembus beberapa hari lalu dan harganya sudah lari jauh setelah itu. Sinyalnya masih
    menyala, tapi stop 2N-mu akan diukur dari harga yang sudah naik — risiko rupiahnya sama,
    entry-nya jauh lebih buruk. Turtle masuk di HARI tembus, bukan belakangan.</div>""",
                unsafe_allow_html=True)

    st.markdown(f"<h3 style='font-family:Orbitron;color:#3d7fff;font-size:16px;letter-spacing:2px;"
                f"margin-top:22px'>MENDEKATI TEMBUS &nbsp;—&nbsp; {len(dekat)} SAHAM</h3>",
                unsafe_allow_html=True)
    st.caption(f"Belum sinyal. Jangan dibeli. Jarak maksimal {ambang_dekat:.1f}% dari level tembus. "
               f"Peluang tembus besok menurut uji 1 tahun: jarak 1% = 25%, 2% = 16%, 3% = 11%, "
               f"5% = 7%, 8% = 4%.")
    if dekat.empty:
        st.info(f"Tidak ada yang dalam jarak {ambang_dekat:.1f}% dari level tembus.")
    else:
        if mode_tampil.startswith("Kartu"):
            sub = dekat if maks_kartu == 0 else dekat.head(int(maks_kartu))
            st.markdown(kartu(sub, kas), unsafe_allow_html=True)
            if len(sub) < len(dekat):
                st.caption(f"{len(sub)} teratas dari {len(dekat)}. "
                           f"Setel 'Maksimal kartu' ke 0 di sidebar untuk menampilkan semua.")
        else:
            st.dataframe(tampil_ringkas(dekat), use_container_width=True, hide_index=True,
                         column_config=KONF, height=min(60 + 35 * len(dekat), 380))

    st.markdown("""<div class="catatan">
    <b>Aplikasi ini tidak tahu apa yang sudah kamu pegang.</b> Saham yang sudah tembus akan terus
    muncul selama harganya masih di atas level itu — bisa berhari-hari. Cocokkan dulu dengan sheet
    OBERLIN di jurnal sebelum membeli, supaya tidak membeli nama yang sama dua kali. Penambahan
    unit hanya sah di kelipatan 0,5N di atas harga masuk pertama, bukan setiap kali sinyal masih menyala.
    </div>""", unsafe_allow_html=True)

    st.download_button("Unduh hasil pindai Turtle (CSV)",
                       d[URUT].rename(columns=KOLOM).to_csv(index=False).encode(),
                       f"turtle_{datetime.now(WIB).strftime('%Y%m%d')}.csv", "text/csv",
                       key="dl_turtle")

with tab2:
    st.markdown(f"""<div class="aturan" style="border-left-color:#a855f7">
    <b>Dua tahap, bukan satu keputusan.</b> Saham harus lolos empat syarat struktur harga Wyckoff DULU
    (re-akumulasi), baru dicek sinyal Turtle. Watchlist di bawah bukan rekomendasi beli — cuma daftar
    kandidat yang strukturnya cocok. Ekuitas dan kas di sini SPRING (akun FUNDAMENTAL), terpisah dari
    OBERLIN.<br>
    <b>Syarat struktur (wajib semua):</b> rally &ge;{rally_min*100:.0f}% sebelum puncak (jendela 150 hari)
    &middot; turun &ge;{turun_min*100:.0f}% dari puncak &middot; sideways &ge;{sideways_min_hari} hari
    &middot; range 15H &le;{range_maks*100:.0f}%<br>
    <b>Volume MA20 &ge;{volume_mult:.1f}x MA50 menentukan TIER, bukan gerbang lolos/gagal:</b>
    volume tinggi &rarr; tier SIAP (absorption klasik). Volume rendah &rarr; tier CEK BROKER FLOW
    (bisa jadi quiet accumulation — big player ngumpulin barang tanpa bikin volume meledak, wajib
    dikonfirmasi manual lewat gauge Broker Action di Stockbit sebelum dianggap kandidat).
    </div>""", unsafe_allow_html=True)

    siap = d[d["tier_siap"]].copy()
    cek_broker = d[d["tier_cek_broker"]].copy()

    if siap.empty and cek_broker.empty:
        st.markdown('<div class="kosong"><div class="kosong-judul">TIDAK ADA KANDIDAT</div>'
                    '<div class="kosong-sub">Tidak ada saham yang lolos empat syarat struktur Wyckoff '
                    'hari ini.<br>Ini keadaan normal — coba longgarkan ambang di sidebar kalau mau lihat '
                    'lebih banyak, atau tunggu hari lain.</div></div>', unsafe_allow_html=True)
    else:
        siap_tembus = siap[siap["tembus"]].sort_values("lari")
        siap_pantau = siap[~siap["tembus"]].sort_values("jarak", ascending=False)

        st.markdown(f"<h3 style='font-family:Orbitron;color:#c084fc;font-size:16px;letter-spacing:2px'>"
                    f"SIAP — SUDAH TEMBUS &nbsp;—&nbsp; {len(siap_tembus)} SAHAM</h3>",
                    unsafe_allow_html=True)
        if siap_tembus.empty:
            st.info("Belum ada kandidat tier SIAP yang sekaligus tembus tertinggi 20 hari hari ini.")
        else:
            st.markdown(kartu_wyckoff(siap_tembus, "siap_tembus"), unsafe_allow_html=True)
            muat_s = siap_tembus[siap_tembus["muat_spring"] == "YA"]
            st.caption(f"{len(muat_s)} dari {len(siap_tembus)} muat di kas SPRING Rp{kas_spring:,.0f}"
                       .replace(",", "."))

        st.markdown(f"<h3 style='font-family:Orbitron;color:#7c3aed;font-size:16px;letter-spacing:2px;"
                    f"margin-top:22px'>SIAP — PANTAU, BELUM TEMBUS &nbsp;—&nbsp; {len(siap_pantau)} SAHAM</h3>",
                    unsafe_allow_html=True)
        if siap_pantau.empty:
            st.info("Tidak ada kandidat tier SIAP lain yang masih menunggu tembus.")
        else:
            st.markdown(kartu_wyckoff(siap_pantau, "siap_pantau"), unsafe_allow_html=True)

        st.markdown(f"<h3 style='font-family:Orbitron;color:#eab308;font-size:16px;letter-spacing:2px;"
                    f"margin-top:22px'>CEK BROKER FLOW — VOLUME SEPI &nbsp;—&nbsp; {len(cek_broker)} SAHAM</h3>",
                    unsafe_allow_html=True)
        st.caption("Struktur harga cocok, tapi volume di bawah ambang. Bisa quiet accumulation, bisa juga "
                   "memang sepi peminat. Cek gauge Broker Action (Big Dist <-> Big Acc) di Stockbit untuk "
                   "tiap kode sebelum menganggap ini kandidat sungguhan.")
        if cek_broker.empty:
            st.info("Tidak ada kandidat di tier ini hari ini.")
        else:
            st.markdown(kartu_wyckoff(cek_broker, "cek_broker"), unsafe_allow_html=True)

        gabungan = pd.concat([siap, cek_broker])
        st.download_button("Unduh watchlist Wyckoff SPRING (CSV)",
                           gabungan.to_csv(index=False).encode(),
                           f"wyckoff_spring_{datetime.now(WIB).strftime('%Y%m%d')}.csv", "text/csv",
                           key="dl_wyckoff")

    st.markdown("""<div class="catatan" style="border-left-color:#a855f7">
    <b>Ini prefilter mekanis, bukan konfirmasi visual.</b> Empat syarat struktur di atas tidak bisa
    membedakan re-akumulasi asli dari distribusi terselubung — itu kerjanya mata, bukan rumus. Cek chart
    tiap kandidat sebelum masuk, terutama yang levelnya (tertinggi 20H / terendah 10H) berdekatan dengan
    harga sekarang. Untuk tier CEK BROKER FLOW, wajib cek gauge Broker Action di Stockbit dulu.<br><br>
    <b>Sizing bukan aturan wajib.</b> Angka "usulan (referensi)" di tiap kartu dihitung dari rumus lama
    (1% ekuitas SPRING ÷ N), tapi keputusan berapa lot yang dibeli sekarang murni insting kamu.
    Wajib dicatat di jurnal: lot rekomendasi aplikasi, lot aktual dibeli, dan alasan bobotnya
    (termasuk kesan tape reading kalau itu yang mendasari) — supaya nanti bisa dievaluasi.
    </div>""", unsafe_allow_html=True)

st.caption("Data Yahoo Finance, tertunda 10-15 menit · N dihitung dengan Wilder 20 hari "
           "sesuai rumus asli Turtle · bukan rekomendasi investasi")
