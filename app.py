"""
REGIME SCREENER
===============
Deteksi fase siklus IHSG (BEAR / BOTTOM-REBOUND / NORMALIZING) + pemburu saham
laggard sektor, dengan bobot ekuitas Rp20 juta all-in ke satu kandidat terbaik.

4 tahap:
    1. Status IHSG   -- fase siklus + backtest probabilitas historis (7 episode sejak 2000)
    2. Status Sektor -- return tiap sektor sejak titik bottom IHSG terakhir
    3. Kandidat Emiten -- gerbang keras -> skor -> tier, dalam sektor yang sudah bergerak
    4. Bobot Ekuitas -- all-in / tie-breaker / cash ditahan / cash menganggur

Jalankan:  streamlit run app.py
Kebutuhan: streamlit yfinance pandas numpy
"""

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Regime Screener", layout="centered")

# =====================================================================
# UNIVERSE -- basket representatif per sektor (bukan 840 emiten penuh)
# =====================================================================
SECTOR_BASKETS = {
    "Barang Baku": ["TPIA", "INTP", "SMGR", "INKP", "ANTM", "INCO", "MDKA",
                    "TINS", "MBMA", "BRPT", "ESSA"],
    "Energi": ["MEDC", "PGAS", "ADRO", "PTBA", "ITMG", "AKRA",
               "HRUM", "INDY", "ELSA", "ADMR"],
    "Perindustrian": ["ASII", "UNTR", "HEXA", "AUTO",
                       "PTRO", "ASGR", "DRMA"],
    "Keuangan": ["BBCA", "BBRI", "BMRI", "BBNI", "BRIS",
                 "BJBR", "BJTM", "BNGA", "NISP"],
    "Konsumer Siklikal": ["MAPI", "ACES", "LPPF", "ERAA",
                          "MYOR", "MIDI", "MAPA"],
    "Properti": ["BSDE", "CTRA", "PWON", "SMRA",
                 "ASRI", "DILD", "APLN"],
    "Kesehatan": ["KLBF", "HEAL", "MIKA", "SIDO"],  # lapis 2 kesehatan terbatas, belum ditambah
}
SEKTOR_FINANSIAL = {"Keuangan"}
PAPAN_PENGEMBANGAN = {"NCKL", "DOID"}  # placeholder -- perlu update manual berkala
ALL_TICKERS = sorted({t for lst in SECTOR_BASKETS.values() for t in lst})

# =====================================================================
# PARAMETER (kalibrasi di sini)
# =====================================================================
BEAR_THRESHOLD = -0.20
REBOUND_TRIGGER = 0.20
NORMALIZING_TRIGGER = 0.20
GAP_SIGNIFIKAN_THRESHOLD = -10.0
BERAT_NAIK_DER_MULTIPLIER = 1.5
BERAT_NAIK_BETA_THRESHOLD = 0.3
BERAT_NAIK_TOP_N_MCAP = 2
BERAT_NAIK_PENALTY = 0.5
PARTICIPATION_VOL_RATIO = 4.0
PARTICIPATION_VALUE_IDR = 100_000_000_000
MODAL_EQUITAS = 20_000_000

# =====================================================================
# PENGAMBILAN DATA -- pola sama seperti Turtle Board: polos, batching,
# cache_data, gagal-lanjut (bukan retry-loop dengan session custom yang
# ternyata malah bikin Yahoo lebih curiga).
# =====================================================================
# =====================================================================
# REFERENSI SIKLUS 2026 -- DATA STATIS (puncak & bottom sudah jadi sejarah)
# =====================================================================
PUNCAK_2026 = 9134.70                         # 20 Jan 2026
TROUGH_2026_HARGA = 5342.14                   # 8 Jun 2026
TROUGH_2026_TANGGAL = pd.Timestamp("2026-06-08")


@st.cache_data(ttl=900, show_spinner=False)
def ambil_harga_ihsg_now():
    """Fungsi ini SALINAN PERSIS ambil_makro() Turtle Board (tickers, period, semua
    parameter sama persis) -- terbukti jalan di server yang sama. Tidak dimodifikasi
    lagi supaya tidak ada lagi tebakan soal parameter mana yang beda.
    Mengembalikan (harga, tanggal, error_message)."""
    peta = {"^JKSE": "IHSG", "IDR=X": "USDIDR", "CL=F": "MINYAK",
            "GC=F": "EMAS", "HG=F": "TEMBAGA", "^IXIC": "NASDAQ"}
    try:
        df = yf.download(list(peta), period="1mo", interval="1d", progress=False,
                         auto_adjust=False, group_by="ticker", threads=True)
        if df is None or df.empty:
            return None, None, f"yf.download mengembalikan dataframe kosong. Shape: {None if df is None else df.shape}"
        if isinstance(df.columns, pd.MultiIndex):
            if "^JKSE" not in df.columns.get_level_values(0):
                return None, None, f"Kolom tidak ada '^JKSE'. Kolom yang ada: {list(df.columns)[:10]}"
            close = df["^JKSE"]["Close"].dropna()
        else:
            close = df["Close"].dropna()
        if len(close) == 0:
            return None, None, "Kolom Close ada tapi semua nilai NaN/kosong setelah dropna()."
        return float(close.iloc[-1]), close.index[-1], None
    except Exception as e:
        import traceback
        return None, None, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"


def status_ihsg_ringan(harga_now, tanggal):
    drawdown_52w = (harga_now - PUNCAK_2026) / PUNCAK_2026 * 100
    pct_dari_trough = (harga_now - TROUGH_2026_HARGA) / TROUGH_2026_HARGA * 100
    if pct_dari_trough >= NORMALIZING_TRIGGER * 100:
        fase = "NORMALIZING"
    elif pct_dari_trough >= REBOUND_TRIGGER * 100:
        fase = "BOTTOM-REBOUND"
    else:
        fase = "BEAR"
    return {"harga": harga_now, "tanggal": tanggal, "drawdown_52w": drawdown_52w,
           "fase": fase, "trough_date": TROUGH_2026_TANGGAL, "pct_dari_trough": pct_dari_trough}


# =====================================================================
# BACKTEST HISTORIS -- DATA STATIS, BUKAN LIVE
# =====================================================================
# 7 episode bear market IHSG (>=20% drawdown) sejak 2000 sudah SELESAI --
# angkanya tidak berubah lagi, jadi tidak perlu ditarik ulang tiap app dibuka
# (itu yang selama ini bikin request besar & rentan gagal). Dihitung sekali
# dari data Yahoo Finance per 30 Agustus 2026 lewat backtest_regime.py.
# Kalau mau di-refresh (misal setelah episode baru selesai/lewat setahun),
# jalankan ulang skrip backtest terpisah lalu update angka di bawah manual --
# bukan bagian dari app yang jalan tiap hari.
BACKTEST_HISTORIS = [
    {"horizon": 20, "n": 7, "avg": -0.8, "pct_pos": 57.0, "worst": -9.6, "mae_avg": -5.0},
    {"horizon": 40, "n": 7, "avg": 4.3, "pct_pos": 86.0, "worst": -1.0, "mae_avg": -5.0},
    {"horizon": 60, "n": 7, "avg": 6.6, "pct_pos": 71.0, "worst": -2.8, "mae_avg": -5.4},
    {"horizon": 120, "n": 7, "avg": 12.2, "pct_pos": 86.0, "worst": -8.8, "mae_avg": -7.1},
]

# Sektor pemimpin historis di fase bottom-rebound (dari episode 2020 & 2025 yang
# datanya tersedia) -- referensi pola, BUKAN jaminan berulang setiap kali.
SEKTOR_HISTORIS_TERCEPAT = ["Barang Baku", "Energi", "Perindustrian"]


@st.cache_data(ttl=900, show_spinner=False)
def ambil_universe(tickers, periode="500d", batch=80):
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
                sub = sub[["Open", "Close", "Volume"]].dropna()
                if len(sub) >= 25:
                    keluar[kode] = sub
            except Exception:
                continue
    return keluar


@st.cache_data(ttl=3600, show_spinner=False)
def ambil_info(ticker):
    try:
        return yf.Ticker(f"{ticker}.JK").info
    except Exception:
        return {}


# =====================================================================
# RSS BERITA -- VERSI SEDERHANA (30 Agu 2026)
# =====================================================================
# Cuma 1 sumber (Google News RSS, tidak perlu scraping tiap situs media satu-satu)
# + keyword dasar. Gerbang keras terpisah dari DER/beta/ukuran -- kalau ketemu
# berita negatif di 5 judul terbaru, saham di-exclude total.
# Fail-open: kalau RSS gagal diakses (bukan soal Yahoo Finance, ini web biasa),
# dianggap TIDAK ada berita negatif -- bukan otomatis exclude. Keterbatasan jujur:
# ini bukan pengecekan konteks/negasi (lihat diskusi RSS Corporate Action sebelumnya),
# jadi bisa salah tangkap ("rugi tahun lalu, kini untung" tetap kena kata "rugi").
# Perlu direview manual kalau ada yang ke-exclude gara-gara ini.
RSS_KEYWORD_NEGATIF = [
    "gagal bayar", "pailit", "bangkrut", "delisting", "suspend", "korupsi",
    "gugatan", "kasus dugaan", "penipuan", "skandal", "pkpu", "rugi besar",
    "turun tajam", "anjlok", "diperiksa", "tersangka",
]

RSS_SITUS_KREDIBEL = ["kontan.co.id", "bisnis.com", "emitennews.com", "katadata.co.id"]

RSS_KEYWORD_POSITIF = [
    "laba naik", "laba melonjak", "untung besar", "ekspansi", "akuisisi",
    "kinerja solid", "rekomendasi beli", "buyback", "dividen jumbo",
    "kontrak baru", "penghargaan", "pulih", "prospek cerah", "genjot produksi",
]


@st.cache_data(ttl=1800, show_spinner=False)
def cek_rss_negatif(ticker):
    """Mengembalikan dict berisi berita PALING BARU (apapun sentimennya) + status exclude.

    Selalu kasih tahu update terakhir apa (judul, tanggal, sentimen) -- bukan cuma pas
    negatif. 5 berita diurutkan ulang berdasarkan tanggal asli (urutan Google News TIDAK
    selalu kronologis murni), lalu cuma berita PALING BARU yang menentukan status:
    kalau yang terbaru negatif -> exclude; kalau sudah "ditutup" berita lebih baru yang
    bersih/positif, tidak exclude lagi -- meski ada berita negatif lebih lama di 5 itu."""
    import email.utils
    import urllib.parse
    import xml.etree.ElementTree as ET
    situs_q = " OR ".join(f"site:{s}" for s in RSS_SITUS_KREDIBEL)
    q = f"saham {ticker} ({situs_q})"
    kosong = {"negatif": False, "judul": None, "tanggal": None, "sentimen": None,
             "n_berita": 0, "gagal": False}
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=id&gl=ID&ceid=ID:id"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(r.content)
        berita = []
        for item in root.findall(".//item")[:5]:
            title_el = item.find("title")
            date_el = item.find("pubDate")
            title = title_el.text if title_el is not None else ""
            tgl_raw = date_el.text if date_el is not None else None
            try:
                tgl = email.utils.parsedate_to_datetime(tgl_raw) if tgl_raw else None
            except Exception:
                tgl = None
            berita.append((title, tgl))
        if not berita:
            return kosong
        berita.sort(key=lambda x: x[1] or pd.Timestamp.min.tz_localize("UTC"), reverse=True)
        judul_terbaru, tgl_terbaru = berita[0]
        judul_lower = judul_terbaru.lower()
        tgl_str = tgl_terbaru.strftime("%d %b %Y") if tgl_terbaru else "tanggal tidak diketahui"

        sentimen = "netral"
        negatif = False
        for kw in RSS_KEYWORD_NEGATIF:
            if kw in judul_lower:
                sentimen = "negatif"
                negatif = True
                break
        if sentimen == "netral":
            for kw in RSS_KEYWORD_POSITIF:
                if kw in judul_lower:
                    sentimen = "positif"
                    break

        return {"negatif": negatif, "judul": judul_terbaru, "tanggal": tgl_str,
               "sentimen": sentimen, "n_berita": len(berita), "gagal": False}
    except Exception:
        return {**kosong, "gagal": True}  # fail-open, ditandai jelas "gagal" bukan "aman"


# =====================================================================
# TAHAP 1 -- FASE IHSG
# =====================================================================
def cari_episode_bear(close):
    roll_max = close.rolling(252, min_periods=50).max()
    drawdown = (close - roll_max) / roll_max
    in_bear = drawdown <= BEAR_THRESHOLD
    raw, start = [], None
    for date, flag in in_bear.items():
        if flag and start is None:
            start = date
        if not flag and start is not None:
            raw.append((start, date)); start = None
    if start is not None:
        raw.append((start, in_bear.index[-1]))
    merged = []
    for s, e in raw:
        if merged and (s - merged[-1][1]).days < 90:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return [(s, e) for s, e in merged if (e - s).days >= 20]


def hitung_episode(close):
    episodes = []
    for peak_date, episode_end in cari_episode_bear(close):
        seg = close[peak_date:episode_end]
        trough_date = seg.idxmin()
        trough_price = seg.min()
        target = trough_price * (1 + REBOUND_TRIGGER)
        after = close[trough_date:]
        hit = after[after >= target]
        if len(hit) == 0:
            continue
        signal_date, signal_price = hit.index[0], hit.iloc[0]
        future = close[close.index > signal_date]
        ep = {"trough_date": trough_date, "signal_date": signal_date,
              "signal_price": signal_price, "ongoing": len(future) < 20}
        if not ep["ongoing"]:
            fwd = {}
            mae = {}
            for h in [20, 40, 60, 120]:
                if len(future) >= h:
                    fwd[h] = (future.iloc[h-1] - signal_price) / signal_price * 100
                    window = future.iloc[:h]
                    mae[h] = (window.min() - signal_price) / signal_price * 100
                else:
                    ep["ongoing"] = True
            ep["forward"] = fwd
            ep["mae"] = mae
        episodes.append(ep)
    return episodes


def ringkas_backtest(episodes):
    completed = [e for e in episodes if not e["ongoing"]]
    rows = []
    for h in [20, 40, 60, 120]:
        rets = [e["forward"][h] for e in completed if h in e.get("forward", {})]
        maes = [e["mae"][h] for e in completed if h in e.get("mae", {})]
        if not rets:
            continue
        rows.append({"horizon": h, "n": len(rets), "avg": np.mean(rets),
                    "pct_pos": sum(1 for r in rets if r > 0) / len(rets) * 100,
                    "worst": min(rets), "mae_avg": np.mean(maes)})
    return rows


def status_ihsg(close, episodes):
    if len(close) == 0:
        return None
    last_price, last_date = close.iloc[-1], close.index[-1]
    roll_max = close.rolling(252, min_periods=50).max()
    dd_now = (last_price - roll_max.iloc[-1]) / roll_max.iloc[-1] * 100
    ongoing = [e for e in episodes if e["ongoing"]]
    out = {"tanggal": last_date, "harga": last_price, "drawdown_52w": dd_now}
    if ongoing:
        ep = ongoing[-1]
        pct_dari_trough = (last_price - close[ep["trough_date"]]) / close[ep["trough_date"]] * 100
        if pct_dari_trough >= NORMALIZING_TRIGGER * 100:
            fase = "NORMALIZING"
        elif pct_dari_trough >= REBOUND_TRIGGER * 100:
            fase = "BOTTOM-REBOUND"
        else:
            fase = "BEAR"
        out.update({"fase": fase, "trough_date": ep["trough_date"], "pct_dari_trough": pct_dari_trough})
    else:
        out.update({"fase": "NORMAL", "trough_date": None, "pct_dari_trough": None})
    return out


def traffic_light(fase, backtest):
    if fase == "BOTTOM-REBOUND":
        return "🟢", "Fase rebound awal — syarat sektor & saham aktif dicari"
    if fase == "NORMALIZING":
        b40 = next((b for b in backtest if b["horizon"] == 40), None)
        if b40 and b40["pct_pos"] >= 70:
            return "🟡", "Sudah lewat fase awal (>20% dari bottom) — masih ada peluang tapi tidak seoptimal fase rebound awal"
        return "🟡", "Fase transisi — perlu lebih selektif"
    if fase == "BEAR":
        return "🔴", "Masih tren turun, belum ada konfirmasi rebound"
    return "🔴", "Tidak ada bear market aktif — strategi ini dirancang khusus untuk fase bottom-rebound"


# =====================================================================
# TAHAP 2 -- SEKTOR
# =====================================================================
def status_sektor(harga_map, trough_date):
    hasil = []
    for sektor, tickers in SECTOR_BASKETS.items():
        rets = []
        for t in tickers:
            if t not in harga_map:
                continue
            s = harga_map[t]["Close"]
            s_after = s[s.index >= trough_date]
            if len(s_after) < 2:
                continue
            rets.append((s_after.iloc[-1] - s_after.iloc[0]) / s_after.iloc[0] * 100)
        if rets:
            hasil.append({"sektor": sektor, "return": float(np.mean(rets)), "n": len(rets)})
    hasil.sort(key=lambda x: -x["return"])
    for i, r in enumerate(hasil):
        r["ranking"] = i + 1
        r["bergerak"] = r["return"] > 0
    return hasil


# =====================================================================
# TAHAP 3 -- KANDIDAT EMITEN
# =====================================================================
def metrik_saham(harga_map, ticker, sector_avg, trough_date):
    if ticker not in harga_map:
        return None
    df = harga_map[ticker]
    close, volume = df["Close"], df["Volume"]
    open_ = df["Open"] if "Open" in df.columns else None
    if len(close) < 25:
        return None
    close_after = close[close.index >= trough_date]
    if len(close_after) < 2:
        return None
    stock_return = (close_after.iloc[-1] - close_after.iloc[0]) / close_after.iloc[0] * 100
    gap = stock_return - sector_avg
    vol_5h, vol_20h = volume.tail(5).mean(), volume.tail(20).mean()
    vol_ratio_5h = vol_5h / vol_20h if vol_20h > 0 else 0
    vol_ratio_today = volume.iloc[-1] / vol_20h if vol_20h > 0 else 0
    low_recent = close.tail(5).min()
    low_prior = close.tail(40).head(20).min() if len(close) >= 40 else close.min()
    higher_low = low_recent > low_prior
    value_sesi_ini = float(close.iloc[-1] * volume.iloc[-1])
    roll_max = close.rolling(min(len(close), 750), min_periods=50).max()
    dd = (close - roll_max) / roll_max * 100
    max_dd = float(dd.min()) if not dd.isna().all() else 0.0
    # candle hari ini hijau atau merah -- volume besar di candle MERAH itu tanda
    # distribusi/jual, bukan akumulasi, meski volume ratio-nya tinggi
    candle_hijau = bool(close.iloc[-1] > open_.iloc[-1]) if open_ is not None else None
    return {
        "gap": gap, "vol_ratio_5h": vol_ratio_5h, "vol_ratio_today": vol_ratio_today,
        "higher_low": higher_low, "value_sesi_ini": value_sesi_ini, "max_dd": max_dd,
        "candle_hijau": candle_hijau,
        "harga_20h": close.tail(20).tolist(), "volume_20h": volume.tail(20).tolist(),
    }


def gerbang_keras(ticker, m, sector_median_dd):
    """Gerbang keras -- gagal salah satu = tidak lolos ke skor sama sekali.
    Ambang drawdown DILONGGARKAN (30 Agu 2026, multiplier 2.0 bukan 1.5) -- krisis
    market-wide bikin banyak saham bagus ikut drawdown dalam karena panic selling,
    bukan masalah perusahaan sendiri. DER (penalti lunak) & RSS (di bawah) yang
    jadi penjaga utama kualitas fundamental, bukan drawdown harga semata."""
    alasan = []
    if ticker in PAPAN_PENGEMBANGAN:
        alasan.append("Papan Pengembangan")
    if sector_median_dd != 0 and m["max_dd"] < sector_median_dd * 2.0:
        alasan.append("drawdown historis ekstrem vs median sektor")
    return alasan


def penalti_berat_naik(ticker, info, sector_der_median, market_caps):
    alasan = []
    der, beta, mcap = info.get("debtToEquity"), info.get("beta"), info.get("marketCap")
    if der is not None and sector_der_median:
        if der > sector_der_median * BERAT_NAIK_DER_MULTIPLIER:
            alasan.append(f"DER {der:.0f} tinggi")
    if beta is not None and abs(beta) < BERAT_NAIK_BETA_THRESHOLD:
        alasan.append(f"beta {beta:.2f} mendekati nol")
    if mcap is not None and market_caps:
        top_n = {t for t, _ in sorted(market_caps.items(), key=lambda x: -x[1])[:BERAT_NAIK_TOP_N_MCAP]}
        if ticker in top_n:
            alasan.append("saham terbesar sektor")
    return alasan


def skor_dan_tier(m, gate, penalty):
    if gate:
        return 0.0, "tidak_lolos"
    gap_score = max(0, min(100, -m["gap"] * 2)) if m["gap"] < 0 else 0
    part_score = (50 if m["vol_ratio_5h"] > 1.0 else 0) + (50 if m["higher_low"] else 0)
    skor = gap_score * 0.60 + part_score * 0.40
    if penalty:
        skor *= BERAT_NAIK_PENALTY
    gap_signifikan = m["gap"] <= GAP_SIGNIFIKAN_THRESHOLD
    partisipasi_ok = m["vol_ratio_5h"] > 1.0 and m["higher_low"]
    if gap_signifikan and partisipasi_ok:
        tier = "kuat"
    elif gap_signifikan:
        tier = "menunggu"
    else:
        tier = "gap_kecil"
    return round(skor, 1), tier


# =====================================================================
# TAHAP 4 -- BOBOT EKUITAS
# =====================================================================
def bobot_ekuitas(kandidat):
    hijau = [c for c in kandidat if c["tier"] == "kuat"]
    if not hijau:
        return {"status": "cash_menganggur", "detail": "Tidak ada kandidat Tier hijau saat ini.", "pilihan": None}
    # Gerbang eksekusi: volume ratio (momentum riil) DAN candle hari ini harus hijau
    # (harga > open) -- volume besar di candle merah itu tanda distribusi/jual, bukan
    # akumulasi, meski volume ratio-nya tinggi. Value tetap ditampilkan di kartu sebagai
    # konteks likuiditas/"lirikan trader", tapi bukan syarat lolos.
    lolos = [c for c in hijau
             if c["m"]["vol_ratio_today"] >= PARTICIPATION_VOL_RATIO
             and c["m"]["candle_hijau"] is True]
    if not lolos:
        vol_saja = [c["ticker"] for c in hijau
                   if c["m"]["vol_ratio_today"] >= PARTICIPATION_VOL_RATIO
                   and c["m"]["candle_hijau"] is False]
        detail = f"{len(hijau)} kandidat Tier hijau, belum ada yang lolos (volume>={PARTICIPATION_VOL_RATIO:.0f}x DAN candle hijau)."
        if vol_saja:
            detail += f" {len(vol_saja)} sempat volume tinggi tapi candle merah ({', '.join(vol_saja)}) -- tidak dihitung, indikasi distribusi bukan akumulasi."
        return {"status": "cash_ditahan", "detail": detail,
               "pilihan": None, "menunggu": [c["ticker"] for c in hijau]}
    if len(lolos) == 1:
        pilihan, alasan = lolos[0], "satu-satunya kandidat lolos eksekusi"
    else:
        tanpa_penalti = [c for c in lolos if not c["penalty"]]
        pool = tanpa_penalti if tanpa_penalti else lolos
        pilihan = max(pool, key=lambda c: c["m"]["vol_ratio_today"])
        kalah = [c["ticker"] for c in lolos if c["ticker"] != pilihan["ticker"]]
        alasan = f"menang tie-breaker (vol {pilihan['m']['vol_ratio_today']:.1f}x) vs {', '.join(kalah)}"
    return {"status": "all_in", "detail": alasan, "pilihan": pilihan["ticker"],
            "kalah": [c["ticker"] for c in lolos if c["ticker"] != pilihan["ticker"]]}


# =====================================================================
# HALAMAN
# =====================================================================
st.title("Regime Screener")

if st.button("🔄 Refresh data"):
    st.cache_data.clear()

@st.fragment(run_every="15m")
def tampilkan_screener():
    with st.spinner("Menarik harga IHSG hari ini..."):
        harga_now, tanggal_now, ihsg_error = ambil_harga_ihsg_now()

    if harga_now is None:
        st.warning("Gagal menarik harga IHSG otomatis dari Yahoo Finance. Masukkan manual dulu supaya tetap bisa dipakai:")
        with st.expander("Detail error (opsional, buat didiagnosis nanti)"):
            st.code(ihsg_error or "Tidak ada pesan error tercatat.")
        harga_now = st.number_input("Harga IHSG hari ini", min_value=0.0, value=6500.0, step=0.01)
        tanggal_now = pd.Timestamp.now().normalize()
        if harga_now <= 0:
            st.stop()

    ihsg = status_ihsg_ringan(harga_now, tanggal_now)
    backtest = BACKTEST_HISTORIS

    # --- Tahap 1
    st.subheader("Tahap 1 — Status IHSG")
    light, note = traffic_light(ihsg["fase"], backtest)
    c1, c2, c3 = st.columns(3)
    c1.metric("Fase", f"{light} {ihsg['fase']}")
    c2.metric("Harga IHSG", f"{ihsg['harga']:.0f}")
    if ihsg["pct_dari_trough"] is not None:
        c3.metric("Dari bottom", f"{ihsg['pct_dari_trough']:+.1f}%")
    st.caption(note)

    with st.expander("Backtest probabilitas historis (7 episode sejak 2000)"):
        st.dataframe(
            [{"Horizon": f"{b['horizon']}h", "Rata² return": f"{b['avg']:+.1f}%",
              "% Positif": f"{b['pct_pos']:.0f}%", "Terburuk": f"{b['worst']:+.1f}%",
              "MAE rata²": f"{b['mae_avg']:+.1f}%"} for b in backtest],
            hide_index=True, width="stretch",
        )
        st.caption("Data statis, dihitung dari histori Yahoo Finance per 30 Agustus 2026 -- "
                  "bukan ditarik ulang tiap app dibuka, karena episode-episode ini sudah selesai.")

    if ihsg["fase"] == "NORMAL" or ihsg["trough_date"] is None:
        st.info("IHSG tidak sedang dalam bear market aktif — Tahap 2-4 tidak relevan saat ini.")
        st.stop()

    # --- ambil data universe (cuma kalau IHSG lagi ada siklus)
    with st.spinner("Menarik data saham universe..."):
        harga_map = ambil_universe(tuple(ALL_TICKERS))

    if not harga_map:
        st.warning("Gagal menarik data saham (Tahap 2-4) dari Yahoo Finance saat ini. "
                  "Tahap 1 di atas tetap bisa dipakai. Tekan Refresh data untuk coba lagi.")
        st.stop()

    # --- Tahap 2
    st.subheader("Tahap 2 — Status Sektor")
    st.caption(f"Referensi historis: sektor yang biasanya paling cepat bergerak di fase bottom-rebound "
              f"adalah {', '.join(SEKTOR_HISTORIS_TERCEPAT)} (dari episode 2020 & 2025) — "
              f"tapi pola tiap siklus bisa beda, cek ranking live di bawah.")
    sektor = status_sektor(harga_map, ihsg["trough_date"])
    for s in sektor:
        status = "🟢 Sudah bergerak" if s["bergerak"] else "⚪ Belum bergerak"
        st.write(f"**#{s['ranking']} {s['sektor']}** — {s['return']:+.1f}% ({s['n']} saham) · {status}")

    sector_return_map = {s["sektor"]: s["return"] for s in sektor}

    # --- Tahap 3
    st.subheader("Tahap 3 — Kandidat Emiten")
    kandidat = []
    for sektor_nama, tickers in SECTOR_BASKETS.items():
        sector_avg = sector_return_map.get(sektor_nama, 0)
        if sector_avg <= 0:
            continue
        dd_values, der_values, market_caps, infos, metrics_map = [], [], {}, {}, {}
        for t in tickers:
            m = metrik_saham(harga_map, t, sector_avg, ihsg["trough_date"])
            if m is None:
                continue
            metrics_map[t] = m
            dd_values.append(m["max_dd"])
            info = ambil_info(t)
            infos[t] = info
            if info.get("marketCap"):
                market_caps[t] = info["marketCap"]
            if sektor_nama not in SEKTOR_FINANSIAL and info.get("debtToEquity"):
                der_values.append(info["debtToEquity"])
        sector_median_dd = float(np.median(dd_values)) if dd_values else 0
        sector_der_median = float(np.median(der_values)) if der_values else None
        for t, m in metrics_map.items():
            gate = gerbang_keras(t, m, sector_median_dd)
            penalty = [] if gate or sektor_nama in SEKTOR_FINANSIAL else penalti_berat_naik(t, infos.get(t, {}), sector_der_median, market_caps)
            skor, tier = skor_dan_tier(m, gate, penalty)
            kandidat.append({"ticker": t, "sektor": sektor_nama, "skor": skor, "tier": tier,
                             "gate": gate, "penalty": penalty, "m": m})

    kandidat.sort(key=lambda c: -c["skor"])

    # Cek RSS negatif -- cuma untuk kandidat yang relevan (tier kuat/menunggu),
    # bukan seluruh universe, biar tidak lambat. Ketemu -> exclude total (gerbang
    # keras terpisah dari DER/beta/ukuran).
    with st.spinner("Cek berita terbaru untuk kandidat teratas..."):
        for c in kandidat:
            if c["tier"] in ("kuat", "menunggu"):
                rss = cek_rss_negatif(c["ticker"])
                c["rss"] = rss
                if rss["negatif"]:
                    c["tier"] = "tidak_lolos"
                    c["gate"] = c["gate"] + [f"RSS negatif ({rss['tanggal']}): {rss['judul']}"]
                    c["skor"] = 0.0

    eq = bobot_ekuitas(kandidat)
    shown_kuat = [c for c in kandidat if c["tier"] == "kuat"]
    shown_menunggu = [c for c in kandidat if c["tier"] == "menunggu"]

    def render_kartu(c):
        if eq["pilihan"] == c["ticker"]:
            badge = "🟢 All-in Rp20jt"
        elif c["ticker"] in eq.get("menunggu", []):
            badge = "🟡 Cash ditahan"
        else:
            badge = {"kuat": "Kandidat kuat", "menunggu": "Menunggu konfirmasi"}.get(c["tier"], c["tier"])
        with st.container(border=True):
            st.write(f"**{c['ticker']}** — {badge}")
            m = c["m"]
            candle_txt = {True: "🟩 candle hijau", False: "🟥 candle merah", None: "candle ?"}[m["candle_hijau"]]
            st.caption(f"{c['sektor']} · Gap vs sektor {m['gap']:+.1f}% · Vol {m['vol_ratio_today']:.1f}x · "
                      f"{candle_txt} · Value Rp{m['value_sesi_ini']/1e9:.0f}M")
            if c["penalty"]:
                st.caption(f"⚠️ Berat naik: {', '.join(c['penalty'])}")
            if c.get("rss", {}).get("gagal"):
                st.caption("📡 RSS: gagal dicek (koneksi bermasalah, bukan berarti aman)")
            elif c.get("rss") and c["rss"]["judul"]:
                emoji_sentimen = {"positif": "🟢", "negatif": "🔴", "netral": "⚪"}.get(c["rss"]["sentimen"], "⚪")
                st.caption(f"📡 Update terakhir ({c['rss']['tanggal']}) {emoji_sentimen} {c['rss']['sentimen']}: {c['rss']['judul']}")
            elif "rss" in c:
                st.caption("📡 RSS: tidak ada berita ditemukan dari Kontan/Bisnis.com/Emitennews/Katadata")
            if eq["pilihan"] == c["ticker"]:
                st.line_chart(m["harga_20h"], height=120)

    if not shown_kuat and not shown_menunggu:
        st.info("Tidak ada kandidat lolos gerbang saat ini.")

    if shown_kuat:
        st.caption(f"Tier kuat · {len(shown_kuat)} kandidat")
        for c in shown_kuat:
            render_kartu(c)

    if shown_menunggu:
        with st.expander(f"Tier menunggu konfirmasi · {len(shown_menunggu)} saham (belum ada sinyal partisipasi)"):
            for c in shown_menunggu:
                render_kartu(c)

    excluded_rss = [c for c in kandidat if c.get("rss", {}).get("negatif")]
    if excluded_rss:
        with st.expander(f"⛔ {len(excluded_rss)} kandidat dibuang karena RSS negatif -- review manual di sini"):
            for c in excluded_rss:
                st.write(f"**{c['ticker']}** ({c['rss']['tanggal']})")
                st.caption(c["rss"]["judul"])

    # --- Tahap 4
    st.subheader("Tahap 4 — Bobot Ekuitas")
    status_icon = {"all_in": "🟢", "cash_ditahan": "🟡", "cash_menganggur": "⚪"}
    st.write(f"{status_icon.get(eq['status'], '')} **{eq['status'].replace('_', ' ').title()}**")
    st.caption(eq["detail"])

    st.divider()
    st.caption(f"Diperbarui: {datetime.now().strftime('%d %b %Y %H:%M')} · "
              "Universe saat ini: basket representatif per sektor (belum universe 840 emiten penuh). "
              "Data historis, bukan sinyal beli/jual. Bukan nasihat keuangan.")

tampilkan_screener()
