# -*- coding: utf-8 -*-
"""
BROKER MAP BOARD — uji trading berbasis peta broker (akun FUNDAMENTAL)

Isi:
  1. AKSI        : daftar aksi hari ini dari rencana di state JSON (pasang / jual / batal / cek TP)
  2. SARINGAN    : 7 kriteria chart + struktur ZigZag ATR (HL / CHoCH) + batas volatilitas,
                   dicoret otomatis bila ada di daftar kecuali / red flag; cek berita BEI -> RSS
  3. PETA BROKER : hasil analisa broker (diisi Claude dari screenshot Stockbit, lewat state JSON)
  4. RENCANA     : chart struktur harian + RR bersih fee & materai per rencana
  5. JURNAL      : catat transaksi, P/L realized, sisa anggaran rugi
  6. PANDUAN     : sketsa pola chart 1 menit + patokan Val jam 09.30
  7. STATE       : unggah / unduh state JSON

Jalankan : streamlit run broker_map_board.py
Butuh    : streamlit>=1.50, yfinance, pandas, numpy, plotly, requests
"""
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
except ImportError:
    yf = None
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    go = None

WIB = timezone(timedelta(hours=7))


# =============================================================================
# 0. TEMA GELAP
# =============================================================================
def ensure_dark_config():
    path = os.path.join(os.getcwd(), ".streamlit", "config.toml")
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('[theme]\nbase = "dark"\nprimaryColor = "#00ff9c"\n'
                    'backgroundColor = "#06080b"\nsecondaryBackgroundColor = "#0d1218"\n'
                    'textColor = "#d7e0ea"\nfont = "monospace"\n')
    except Exception:
        pass


ensure_dark_config()

COL = dict(text="#d7e0ea", mute="#7d8a99", green="#00c97b", red="#ff4d5e", amber="#f5a623",
           cyan="#2bd9ff", violet="#a78bfa", grid="#1b2430", bg="#06080b", panel="#0d1218")

# =============================================================================
# 1. PARAMETER
# =============================================================================
FEE_BELI = 0.0015
FEE_JUAL = 0.0025
MATERAI = 10_000
MATERAI_AMBANG = 10_000_000          # tiap transaksi di atas Rp10 jt kena materai
VAL_MIN = 5e9                        # nilai transaksi rata-rata 20 hari minimal
POS_MAX = 40.0                       # posisi di range YTD maksimal (%)
DIST_MAX = 1.5                       # jarak ke support maksimal (x ATR)
STOCH_LV = 20.0                      # stochastic %K(14,3)
R20_MAX = 20.0                       # kenaikan 20 hari maksimal (%)
BOUNCE_MAX = 3.0                     # pantulan dari low crash maksimal (x ATR)
SL_ATR = 1.5                         # SL minimal 1,5 x ATR dari entry
SL_MAX_PCT = 10.0                    # 1,5 x ATR + fee maksimal 10% (batas volatilitas)
STRUCT_MULT = 1.0                    # ZigZag struktur: swing terkunci saat harga berbalik >= 1 x ATR
CRASH_DATE = "2026-10-16"            # awal crash MSCI; pantulan dihitung dari low sejak tanggal ini
VAL_0930 = 0.20                      # patokan value jam 09.30 = 20% rata-rata harian 20 hari
RITEL = {"XL", "YP", "PD", "XC"}
RED_FLAG = set("AGAR DOOH BIKE AYAM MGLV VISI JARR PGUN TEBE MDIA SINI FORU PIPA JGLE "
               "VKTR SGER IRSX BREN TPIA MMIX PEGE MEJA PACK".split())
KATA_KUNCI = {
    "BUYBACK": r"buyback|beli kembali|pembelian kembali",
    "RIGHTS": r"rights issue|hmetd|penawaran umum terbatas",
    "PRIVATE PLACEMENT": r"private placement|tanpa hmetd|pmthmetd",
    "OJK/SANKSI": r"\bojk\b|sanksi|denda|manipulasi",
    "SUSPENSI/UMA": r"suspensi|suspend|\buma\b|unusual market",
    "TENDER OFFER": r"tender offer|penawaran tender",
}

UNIVERSE = """
AADI AALI ABBA ABDA ABMM ACES ACRO ACST ADCP ADES ADHI ADMF ADMG ADMR ADRO AEGS AGAR AGII
AGRO AGRS AHAP AIMS AISA AKKU AKPI AKRA AKSI ALDO ALII ALKA ALMI ALTO AMAG AMAN AMAR AMFG
AMIN AMMN AMMS AMOR AMRT ANDI ANJT ANTM APEX APIC APII APLI APLN ARCI AREA ARGO ARII ARKA
ARKO ARMY ARNA ARTA ARTI ARTO ASBI ASDM ASGR ASHA ASII ASJT ASLC ASLI ASMI ASPI ASPR ASRI
ASRM ASSA ATAP ATIC ATLA AUTO AVIA AWAN AXIO AYAM AYLS BABP BABY BACA BACH BAIK BAJA BALI
BANK BAPA BAPI BATA BATR BAUT BAYU BBCA BBHI BBKP BBLD BBMD BBNI BBRI BBRM BBSI BBSS BBTN
BBYB BCAP BCIC BCIP BDKR BDMN BEBS BEEF BEER BEKS BELI BELL BESS BEST BFIN BGTG BHAT BHIT
BIKA BIKE BIMA BINA BINO BIPI BIPP BIRD BISI BJBR BJTM BKDP BKSL BKSW BLES BLOG BLTA BLTZ
BLUE BMAS BMBL BMHS BMRI BMSR BMTR BNBA BNBR BNGA BNII BNLI BOAT BOBA BOGA BOLA BOLT BOSS
BPFI BPII BPTR BRAM BREN BRIS BRMS BRNA BRPT BRRC BSBK BSDE BSIM BSML BSSR BSWD BTEK BTEL
BTON BTPN BTPS BUAH BUDI BUKA BUKK BULL BUMI BUVA BVIC BWPT BYAN CAKK CAMP CANI CARE CARS
CASA CASH CASS CBDK CBMF CBPE CBRE CBUT CCSI CDIA CEKA CENT CFIN CGAS CHEK CHEM CHIP CINT
CITA CITY CLAY CLEO CLPI CMNP CMNT CMPP CMRY CNKO CNMA CNTX COAL COCO COIN COWL CPIN CPRI
CPRO CRAB CRSN CSAP CSIS CSMI CSRA CTBN CTRA CTTH CUAN CYBR DAAZ DADA DART DATA DAYA DCII
DEAL DEFI DEPO DEWA DEWI DFAM DGIK DGNS DGWG DIGI DILD DIVA DKFT DKHH DLTA DMAS DMMX DMND
DNAR DNET DOID DOOH DOSS DPNS DPUM DRMA DSFI DSNG DSSA DUCK DUTI DVLA DWGL DYAN EAST ECII
EDGE EKAD ELIT ELPI ELSA ELTY EMAS EMDE EMMI EMTK ENAK ENRG ENVY ENZO EPAC EPMT ERAA ERAL
ERTX ESIP ESSA ESTA ESTI ETWA EURO EXCL FAPA FAST FASW FILM FIMP FIRE FISH FITT FLMC FMII
FOLK FOOD FORE FORU FORZ FPNI FREN FUJI FUTR FWCT GAMA GDST GDYR GEMA GEMS GGRM GGRP GHON
GIAA GJTL GLOB GLVA GMFI GMTD GOLD GOLF GOLL GOOD GOTO GPRA GPSO GRIA GRPH GRPM GSMF GTBO
GTRA GTSI GULA GUNA GWSA GZCO HADE HAIS HAJJ HALO HATM HBAT HDFA HDIT HDTX HEAL HELI HERO
HEXA HGII HILL HITS HKMU HMSP HOKI HOME HOMI HOPE HOTL HRME HRTA HRUM HUMI HYGN IATA IBFN
IBOS IBST ICBP ICON IDEA IDPR IFII IFSH IGAR IIKP IKAI IKAN IKBI IKPM IMAS IMJS IMPC INAF
INAI INCF INCI INCO INDF INDO INDR INDS INDX INDY INET INKP INOV INPC INPP INPS INRU INTA
INTD INTP IOTF IPAC IPCC IPCM IPOL IPPE IPTV IRRA IRSX ISAP ISAT ISEA ISSP ITIC ITMA ITMG
JARR JAST JATI JAWA JAYA JECC JECX JELI JGLE JIHD JKON JKSW JMAS JPFA JRPT JSKY JSMR JSPT
JTPE KAEF KAQI KARW KAYU KBAG KBLI KBLM KBLV KBRI KDSI KDTN KEEN KEJU KETR KIAS KICI KIJA
KING KINO KIOS KJEN KKES KKGI KLAS KLBF KLIN KMDS KMTR KOBX KOCI KOIN KOKA KONI KOPI KOTA
KPAL KPAS KPIG KRAH KRAS KREN KRYA KSIX KUAS LABA LABS LAJU LAND LAPD LCGP LCKM LEAD LFLO
LIFE LINK LION LIVE LMAS LMAX LMPI LMSH LOPI LPCK LPGI LPIN LPKR LPLI LPPF LPPS LRNA LSIP
LTLS LUCK LUCY MABA MAGP MAHA MAIN MAMI MANG MAPA MAPB MAPI MARI MARK MASA MASB MAXI MAYA
MBAP MBMA MBSS MBTO MCAS MCOL MCOR MDIA MDIY MDKA MDKI MDLA MDLN MDRN MEDC MEDS MEGA MEJA
MENN MERK META MFIN MFMI MGLV MGNA MGRO MHKI MICE MIDI MIKA MINA MINE MIRA MITI MKAP MKNT
MKPI MKTR MLBI MLIA MLPL MLPT MMIX MMLP MNCN MOLI MORA MPIX MPMX MPOW MPPA MPRO MPXL MRAT
MREI MSIE MSIN MSJA MSKY MSTI MTDL MTEL MTFN MTLA MTMH MTPS MTRA MTSM MTWI MUTU MYOH MYOR
MYRX MYTX NAIK NANO NASA NASI NATO NAYZ NCKL NELY NEST NETV NFCX NICE NICK NICL NIKL NINE
NIPS NIRO NISP NOBU NPGF NRCA NSSS NTBK NUSA NZIA OASA OBAT OBMD OCAP OILS OKAS OLIV OMED
OMRE OPMS PACK PADA PADI PALM PAMG PANI PANR PANS PART PBID PBRX PBSA PCAR PDES PDPP PEGE
PEHA PEVE PGAS PGEO PGJO PGLI PGUN PICO PIPA PJAA PJHB PKPK PLAN PLAS PLIN PMJS PMMP PMUI
PNBN PNBS PNGO PNIN PNLF PNSE POLA POLI POLL POLU POLY POOL PORT POSA POWR PPGL PPRE PPRI
PPRO PRAS PRAY PRDA PRDL PRIM PSAB PSAT PSDN PSGO PSKT PSSI PTBA PTDU PTIS PTMP PTMR PTPP
PTPS PTPW PTRO PTSN PTSP PUDP PURA PURE PURI PWON PYFA PZZA RAAM RAFI RAJA RALS RANC RANS
RATU RBMS RCCC RDTX REAL RELF RELI RGAS RICY RIGS RIMO RISE RLCO RMKE RMKO ROCK RODA RONY
ROTI RSCH RSGK RUIS RUNS SAFE SAGE SAME SAMF SAPX SATU SBAT SBMA SCCO SCMA SCNP SCPI SDMU
SDPC SDRA SEMA SFAN SGER SGRO SHID SHIP SICO SIDO SILO SIMA SIMP SINI SIPD SKBM SKLT SKRN
SKYB SLIS SMAR SMBR SMCB SMDM SMDR SMGA SMGR SMIL SMKL SMKM SMLE SMMA SMMT SMRA SMRU SMSM
SNLK SOCI SOFA SOHO SOLA SONA SOSS SOTS SOUL SPMA SPRE SPTO SQMI SRAJ SRIL SRSN SRTG SSIA
SSMS SSTM STAA STAR STRK STTP SUGI SULI SUNI SUPA SUPR SURE SURI SWAT SWID TALF TAMA TAMU
TAPG TARA TAXI TAYS TBIG TBLA TBMS TCID TCPI TDPM TEBE TECH TELE TFAS TFCO TGKA TGRA TGUK
TIFA TINS TIRA TIRT TKIM TLDN TLKM TMAS TMPO TNCA TOBA TOOL TOPS TOSK TOTL TOTO TOWR TOYS
TPIA TPMA TRAM TRGU TRIL TRIM TRIN TRIO TRIS TRJA TRON TRST TRUE TRUK TRUS TSPC TUGU TYRE
UANG UCID UDNG UFOE ULTJ UNIC UNIQ UNIT UNSP UNTD UNTR UNVR URBN UVCR VAST VERN VICI VICO
VINS VISI VIVA VKTR VOKS VRNA VTNY WAPO WBSA WEGE WEHA WGSH WICO WIDI WIFI WIIM WIKA WINE
WINR WINS WIRG WMPP WMUU WOMF WOOD WOWS WSBP WSKT WTON XSPI YELO YOII YPAS YULE YUPI ZATA
ZBRA ZINC ZONE ZYRX
"""
TICKERS = tuple(sorted(set(UNIVERSE.split())))


# =============================================================================
# 2. UTILITAS HARGA
# =============================================================================
def tick_size(p):
    if p < 200:
        return 1
    if p < 500:
        return 2
    if p < 2000:
        return 5
    if p < 5000:
        return 10
    return 25


def round_down_tick(p):
    t = tick_size(p)
    return math.floor(p / t) * t


def rp(x, dec=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def jt(x):
    return "-" if x is None else f"{rp(x / 1e6, 2)} jt"


def materai(nilai):
    return MATERAI if nilai > MATERAI_AMBANG else 0


def atr_wilder(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().values


def stoch_k(h, l, c, n=14, sm=3):
    hh = pd.Series(h).rolling(n).max()
    ll = pd.Series(l).rolling(n).min()
    k = 100 * (pd.Series(c) - ll) / (hh - ll)
    return k.rolling(sm).mean().values


def zigzag_atr(h, l, atr, mult):
    """ZigZag berbasis ATR (sama dengan Harmonic Board)."""
    n = len(h)
    valid = np.where(~np.isnan(atr))[0]
    if len(valid) == 0:
        return [], None
    s = valid[0]
    piv = []
    trend = 0
    hi, hi_i, lo, lo_i = h[s], s, l[s], s
    ext, ext_i = None, None
    for i in range(s + 1, n):
        th = mult * atr[i]
        if trend == 0:
            if h[i] > hi:
                hi, hi_i = h[i], i
            if l[i] < lo:
                lo, lo_i = l[i], i
            if lo_i < i and h[i] - lo >= th:
                piv.append((lo_i, lo, "L"))
                seg = h[lo_i + 1:i + 1]
                k = int(np.argmax(seg))
                ext, ext_i, trend = seg[k], lo_i + 1 + k, 1
            elif hi_i < i and hi - l[i] >= th:
                piv.append((hi_i, hi, "H"))
                seg = l[hi_i + 1:i + 1]
                k = int(np.argmin(seg))
                ext, ext_i, trend = seg[k], hi_i + 1 + k, -1
        elif trend == 1:
            if h[i] > ext:
                ext, ext_i = h[i], i
            elif ext - l[i] >= th:
                piv.append((ext_i, ext, "H"))
                seg = l[ext_i + 1:i + 1]
                k = int(np.argmin(seg))
                ext, ext_i, trend = seg[k], ext_i + 1 + k, -1
        else:
            if l[i] < ext:
                ext, ext_i = l[i], i
            elif h[i] - ext >= th:
                piv.append((ext_i, ext, "L"))
                seg = h[ext_i + 1:i + 1]
                k = int(np.argmax(seg))
                ext, ext_i, trend = seg[k], ext_i + 1 + k, 1
    tent = None
    if trend != 0:
        tent = (ext_i, ext, "H" if trend == 1 else "L")
    return piv, tent


def struktur(h, l, c, atr):
    """Status struktur dari dua low terakhir dan swing high di antaranya.
    BELUM  : low terakhir lebih rendah (masih lower low)
    HL     : higher low terbentuk, harga di atas HL, belum tutup di atas swing high
    CHOCH  : higher low terbentuk dan harga tutup di atas swing high di antara dua low
    RUSAK  : higher low terbentuk tapi harga tutup di bawahnya
    """
    piv, tent = zigzag_atr(h, l, atr, STRUCT_MULT)
    pts = list(piv) + ([tent] if tent else [])
    lows = [p for p in pts if p[2] == "L"]
    out = dict(status="?", sweep=None, hl=None, choch=None, pts=pts)
    if len(lows) < 2:
        return out
    l1, l2 = lows[-2], lows[-1]
    mid = [p for p in pts if p[2] == "H" and l1[0] < p[0] < l2[0]]
    if not mid:
        return out
    hsw = max(mid, key=lambda p: p[1])
    close = c[-1]
    out.update(sweep=float(l1[1]), hl=float(l2[1]), choch=float(hsw[1]),
               i_sweep=l1[0], i_hl=l2[0], i_choch=hsw[0])
    if l2[1] <= l1[1]:
        out["status"] = "BELUM"
    elif close < l2[1]:
        out["status"] = "RUSAK"
    elif close > hsw[1]:
        out["status"] = "CHOCH"
    else:
        out["status"] = "HL"
    return out


# =============================================================================
# 3. DATA
# =============================================================================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_all(tickers):
    if yf is None:
        return {}
    start = (datetime.now(WIB) - timedelta(days=430)).strftime("%Y-%m-%d")
    out = {}
    tk = list(tickers)
    for i in range(0, len(tk), 100):
        b = [t + ".JK" for t in tk[i:i + 100]]
        try:
            d = yf.download(b, start=start, progress=False, group_by="ticker",
                            auto_adjust=False, threads=True)
        except Exception:
            continue
        for t in tk[i:i + 100]:
            try:
                x = d[t + ".JK"][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(x):
                    x.index = pd.to_datetime(x.index).tz_localize(None)
                    out[t] = x
            except Exception:
                pass
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_one(t):
    if yf is None:
        return None
    start = (datetime.now(WIB) - timedelta(days=430)).strftime("%Y-%m-%d")
    try:
        x = yf.download(t + ".JK", start=start, progress=False, auto_adjust=False)
        if isinstance(x.columns, pd.MultiIndex):
            x.columns = x.columns.get_level_values(0)
        x = x[["Open", "High", "Low", "Close", "Volume"]].dropna()
        x.index = pd.to_datetime(x.index).tz_localize(None)
        return x if len(x) else None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ihsg():
    if yf is None:
        return None
    try:
        x = yf.download("^JKSE", period="3mo", progress=False, auto_adjust=False)
        if isinstance(x.columns, pd.MultiIndex):
            x.columns = x.columns.get_level_values(0)
        return x.dropna()
    except Exception:
        return None


def analisa(t, x):
    """Semua angka saringan untuk satu saham. None kalau data tidak cukup."""
    if x is None or len(x) < 120:
        return None
    o, h, l, c, v = (x[k].values.astype(float) for k in ["Open", "High", "Low", "Close", "Volume"])
    atr = atr_wilder(h, l, c)
    a, C = atr[-1], c[-1]
    if np.isnan(a) or a <= 0:
        return None
    val20 = float(np.mean(c[-20:] * v[-20:]))
    y = x[x.index >= f"{x.index[-1].year}-01-01"]
    hi, lo = float(y["High"].max()), float(y["Low"].min())
    pos = (C - lo) / (hi - lo) * 100 if hi > lo else np.nan
    L = l[-120:]
    piv = [L[i] for i in range(2, len(L) - 2) if L[i] == L[i - 2:i + 3].min()]
    cand = [p for p in piv + [float(l[-5:-1].min())] if p < C]
    sup = max(cand) if cand else float(L.min())
    dist = (C - sup) / a
    k = stoch_k(h, l, c)
    K, Kmin = k[-1], pd.Series(k[-6:-1]).min()
    if any(isinstance(v, float) and math.isnan(v) for v in (pos, K, Kmin)) or pd.isna(K) or pd.isna(Kmin):
        return None
    st_ok = (K < STOCH_LV) or (Kmin < STOCH_LV and K > Kmin)
    r20 = (C / c[-21] - 1) * 100
    crash = x.loc[x.index >= CRASH_DATE, "Low"]
    bounce = (C - float(crash.min())) / a if len(crash) else 0.0
    sl_pct = SL_ATR * a / C * 100 + (FEE_BELI + FEE_JUAL) * 100
    g = (x["Open"] / x["Close"].shift() - 1).abs()
    gy = g[(g.index >= y.index[0]) & (g.index != CRASH_DATE)]
    curiga = bool((gy > 0.16).any() or (y["Close"] % 1 != 0).any())
    s = struktur(h, l, c, atr)
    kri = {"Range<40%": pos < POS_MAX, "Support≤1,5ATR": dist <= DIST_MAX, "Stoch": bool(st_ok),
           "Tak kejar": (r20 <= R20_MAX) and (bounce <= BOUNCE_MAX), "Likuid": val20 > VAL_MIN,
           "SL≤10%": sl_pct <= SL_MAX_PCT}
    return dict(Kode=t, Harga=C, Tanggal=x.index[-1].strftime("%Y-%m-%d"), **{"Range %": round(pos),
                "ATR": round(a, 1), "ATR %": round(a / C * 100, 1), "Support": sup, "Jarak xATR": round(dist, 2),
                "Stoch K": round(float(K), 1), "Naik 20H %": round(r20, 1), "Pantul xATR": round(bounce, 1),
                "Val 20H (M)": round(val20 / 1e9, 1), "SL 1,5ATR %": round(sl_pct, 1),
                "Struktur": s["status"], "HL": s["hl"], "CHoCH": s["choch"], "Sweep": s["sweep"],
                "Data curiga": curiga, "Lolos": sum(kri.values()), "_kri": kri,
                "Val 09.30 (M)": round(val20 * VAL_0930 / 1e9, 1)})


# =============================================================================
# 4. BERITA: BEI dulu, lalu Google News RSS
# =============================================================================
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Referer": "https://www.idx.co.id/"}


def flag_teks(teks):
    t = teks.lower()
    return [k for k, pat in KATA_KUNCI.items() if re.search(pat, t)]


@st.cache_data(ttl=3600, show_spinner=False)
def idx_stock_summary(tanggal):
    """Ringkasan perdagangan BEI per saham (Foreign Buy/Sell). Endpoint tidak resmi; bisa diblokir."""
    url = ("https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
           f"?length=9999&start=0&date={tanggal}")
    try:
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200:
            return None, f"BEI HTTP {r.status_code}"
        js = r.json()
        rows = js.get("data") or js.get("Data") or []
        if not rows:
            return None, "BEI: data kosong"
        df = pd.DataFrame(rows)
        need = {"StockCode", "ForeignBuy", "ForeignSell", "Close"}
        if not need.issubset(df.columns):
            return None, "BEI: format kolom berubah"
        df = df[list(need)].copy()
        for k in ["ForeignBuy", "ForeignSell", "Close"]:
            df[k] = pd.to_numeric(df[k], errors="coerce")
        df["Net asing (lembar)"] = df["ForeignBuy"] - df["ForeignSell"]
        df["Net asing ~Rp M"] = (df["Net asing (lembar)"] * df["Close"] / 1e9).round(2)
        return df.set_index("StockCode"), "BEI OK"
    except Exception as ex:
        return None, f"BEI gagal: {type(ex).__name__}"


@st.cache_data(ttl=3600, show_spinner=False)
def idx_pengumuman(kode):
    dari = (datetime.now(WIB) - timedelta(days=45)).strftime("%Y%m%d")
    ke = datetime.now(WIB).strftime("%Y%m%d")
    url = ("https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"
           f"?kodeEmiten={kode}&emitenType=*&indexFrom=0&pageSize=20&dateFrom={dari}&dateTo={ke}&lang=id&keyword=")
    try:
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200:
            return None
        js = r.json()
        out = []

        def jalan(o):
            if isinstance(o, dict):
                judul = o.get("JudulPengumuman") or o.get("Title")
                if judul:
                    out.append(dict(tanggal=str(o.get("TglPengumuman", ""))[:10], judul=judul,
                                    sumber="BEI", link=""))
                for vv in o.values():
                    jalan(vv)
            elif isinstance(o, list):
                for vv in o:
                    jalan(vv)
        jalan(js)
        return out
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def rss_berita(kode):
    q = (f'"{kode}" (buyback OR "rights issue" OR "private placement" OR OJK OR suspensi OR "tender offer")'
         " when:30d")
    url = "https://news.google.com/rss/search"
    try:
        r = requests.get(url, params=dict(q=q, hl="id", gl="ID", ceid="ID:id"), headers=UA, timeout=15)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content)
        out = []
        for it in root.iter("item"):
            judul = (it.findtext("title") or "").strip()
            out.append(dict(tanggal=(it.findtext("pubDate") or "")[:16], judul=judul, sumber="RSS",
                            link=it.findtext("link") or ""))
        return out
    except Exception:
        return None


def cek_berita(kode):
    """Coba BEI dulu; kalau gagal/kosong pakai RSS. Kembalikan (sumber, daftar berita bertanda)."""
    item = idx_pengumuman(kode)
    sumber = "BEI"
    if not item:
        item = rss_berita(kode)
        sumber = "RSS"
    if item is None:
        return "GAGAL", [], 0
    hasil, dibuang = [], 0
    pola_kode = re.compile(rf"\b{re.escape(kode)}\b", re.IGNORECASE)
    for b in item:
        f = flag_teks(b["judul"])
        if not f:
            continue
        if sumber == "RSS" and not pola_kode.search(b["judul"]):
            dibuang += 1          # judul tidak menyebut kode saham -> berita pasar umum, dibuang
            continue
        hasil.append(dict(b, tanda=", ".join(f)))
    return sumber, hasil, dibuang


# =============================================================================
# 5. STATE
# =============================================================================
def state_kosong():
    return {"versi": 1, "disimpan": None, "akun": "FUNDAMENTAL", "anggaran_rugi": 100_000_000,
            "ukuran_posisi": 25_000_000, "rencana": [], "peta_broker": {}, "pantau": [],
            "kecuali": {}, "log_transaksi": []}


def muat_state(js):
    s = state_kosong()
    s.update({k: v for k, v in js.items() if k in s})
    return s


ss = st.session_state
if "state" not in ss:
    ss["state"] = state_kosong()
    path0 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_broker_map.json")
    if os.path.exists(path0):
        try:
            with open(path0, encoding="utf-8") as f:
                ss["state"] = muat_state(json.load(f))
            ss["auto_src"] = "state_broker_map.json di repo"
        except Exception:
            ss["auto_src"] = "GAGAL membaca state_broker_map.json"
S = ss["state"]


def kecuali_aktif(kode, hari):
    e = S["kecuali"].get(kode)
    if kode in RED_FLAG:
        return "red flag"
    if not e:
        return None
    sampai = e.get("sampai")
    if sampai and hari > sampai:
        return None
    return e.get("alasan", "kecuali")


# =============================================================================
# 6. HITUNGAN RENCANA (fee + materai + pembulatan lot)
# =============================================================================
def bagi_lot(total, porsi):
    lots = [int(round(total * p)) for p in porsi]
    lots[0] += total - sum(lots)
    return lots


def hitung_rr(entries, tps, sl):
    """entries: [(harga, lot)], tps: [(harga, porsi)]. Rugi & untung bersih fee + materai per transaksi."""
    total = sum(lt for _, lt in entries)
    if total <= 0:
        return None
    sh = total * 100
    biaya = sum(lt * 100 * p * (1 + FEE_BELI) + materai(lt * 100 * p) for p, lt in entries)
    avg = sum(lt * p for p, lt in entries) / total
    nsl = sl * sh
    rugi = biaya - (nsl * (1 - FEE_JUAL) - materai(nsl))
    lots = bagi_lot(total, [pr for _, pr in tps])
    per_tp = []
    for (tp, _), lt in zip(tps, lots):
        n = lt * 100 * tp
        per_tp.append(dict(tp=tp, lot=lt, untung_bila_semua=(sh * tp * (1 - FEE_JUAL) - materai(sh * tp)) - biaya,
                           bersih=n * (1 - FEE_JUAL) - materai(n)))
    untung = sum(d["bersih"] for d in per_tp) - biaya
    for d in per_tp:
        d["rr"] = d["untung_bila_semua"] / rugi if rugi > 0 else np.nan
    return dict(lot=total, avg=avg, biaya=biaya, rugi=rugi, untung=untung,
                rr=untung / rugi if rugi > 0 else np.nan, per_tp=per_tp)


def lot_pegang(r):
    return sum(e.get("lot", 0) for e in r.get("terisi", [])) - sum(e.get("lot", 0) for e in r.get("terjual", []))


def evaluasi(r, x, hari):
    """Daftar aksi untuk satu rencana, dicek terhadap bar harian terakhir."""
    aksi = []
    if x is None or not len(x):
        return [("CEK DATA", "Data harga tidak tersedia")]
    bar = x.iloc[-1]
    C, H, Lw = float(bar["Close"]), float(bar["High"]), float(bar["Low"])
    pegang = lot_pegang(r)
    batas = r.get("batas_waktu")
    hl, ch, sl = r.get("hl"), r.get("choch"), r.get("sl")
    tps = r.get("tp", [])
    if r.get("status") in ("SELESAI", "BATAL"):
        return []
    if pegang <= 0:
        if batas and hari > batas:
            aksi.append(("BATAL", f"Lewat batas waktu {batas}, entry belum terisi"))
        elif hl and C < hl:
            aksi.append(("BATAL", f"Tutup {rp(C)} di bawah HL {rp(hl)}: struktur rusak"))
        else:
            for e in r.get("entry", []):
                syarat = f" ({e['syarat']})" if e.get("syarat") else ""
                aksi.append(("PASANG", f"Beli {e['lot']} lot @{rp(e['harga'])}{syarat}"))
            aksi.append(("PRE-OPEN", r.get("aturan_preopen", "Cek harga pembukaan teoretis 08.45–08.58")))
        return aksi
    if sl and Lw <= sl:
        aksi.append(("JUAL SL", f"Low {rp(Lw)} menyentuh SL {rp(sl)}: pastikan {pegang} lot sudah terjual"))
    if hl and C < hl:
        aksi.append(("KELUAR DINI", f"Tutup {rp(C)} di bawah HL {rp(hl)}"))
    sudah = {round(float(t.get("harga", 0))) for t in r.get("terjual", [])}
    for i, t in enumerate(tps):
        if H >= t["harga"] and round(t["harga"]) not in sudah:
            aksi.append(("CEK TP", f"High {rp(H)} menyentuh TP{i + 1} {rp(t['harga'])}: catat penjualan"))
    if batas and hari >= batas:
        tp1_kena = bool(tps) and round(tps[0]["harga"]) in sudah
        if not tp1_kena:
            aksi.append(("JUAL WAKTU", f"Batas waktu {batas} tercapai tanpa TP1: jual {pegang} lot"))
    if ch and C > ch:
        aksi.append(("CHoCH", f"Tutup {rp(C)} di atas {rp(ch)}: konfirmasi, tahap berikutnya boleh dipasang"))
    if not aksi:
        aksi.append(("TAHAN", f"Pegang {pegang} lot · tutup {rp(C)} · SL {rp(sl)} · HL {rp(hl)}"))
    return aksi


# =============================================================================
# 7. GRAFIK
# =============================================================================
def gaya(fig, h=360, judul=None):
    fig.update_layout(template="plotly_dark", height=h, paper_bgcolor=COL["bg"], plot_bgcolor=COL["panel"],
                      margin=dict(l=10, r=10, t=40 if judul else 10, b=10), title=judul,
                      font=dict(family="monospace", color=COL["text"], size=12), showlegend=False)
    fig.update_xaxes(gridcolor=COL["grid"])
    fig.update_yaxes(gridcolor=COL["grid"])
    return fig


def chart_struktur(x, r, s):
    n = min(70, len(x))
    d = x.iloc[-n:]
    fig = go.Figure(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                   increasing_line_color=COL["green"], decreasing_line_color=COL["red"]))
    off = len(x) - n
    pts = [(p[0], p[1]) for p in s.get("pts", []) if p[0] >= off]
    if pts:
        fig.add_trace(go.Scatter(x=[x.index[i] for i, _ in pts], y=[v for _, v in pts], mode="lines+markers",
                                 line=dict(color=COL["cyan"], width=1.5), marker=dict(size=6)))
    garis = []
    for e in (r or {}).get("entry", []):
        garis.append((e["harga"], f"Entry {rp(e['harga'])} ({e['lot']} lot)", COL["text"], "dot"))
    if r and r.get("sl"):
        garis.append((r["sl"], f"SL {rp(r['sl'])}", COL["red"], "dash"))
    for i, t in enumerate((r or {}).get("tp", [])):
        garis.append((t["harga"], f"TP{i + 1} {rp(t['harga'])}", COL["green"], "dash"))
    hl = (r or {}).get("hl") or s.get("hl")
    ch = (r or {}).get("choch") or s.get("choch")
    if hl:
        garis.append((hl, f"HL {rp(hl)}", COL["violet"], "dot"))
    if ch:
        garis.append((ch, f"CHoCH {rp(ch)}", COL["amber"], "dash"))
    for y, lab, warna, dash in garis:
        fig.add_hline(y=y, line=dict(color=warna, width=1, dash=dash), annotation_text=lab,
                      annotation_position="right", annotation_font=dict(color=warna, size=11))
    fig.update_layout(xaxis_rangeslider_visible=False)
    return gaya(fig, 460)


def chart_bar(labels, values, judul, warna=None, h=300, ytitle=None):
    warna = warna or [COL["green"] if v >= 0 else COL["red"] for v in values]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=warna, text=[rp(v, 2) for v in values],
                           textposition="outside"))
    fig.update_yaxes(title=ytitle)
    return gaya(fig, h, judul)


def chart_panduan():
    fig = make_subplots(rows=2, cols=3, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.04,
                        subplot_titles=("Akumulasi", "Distribusi", "Netral"))
    xs = list(range(11))
    pola = {
        1: ([108, 122, 110, 118, 108, 104, 98, 102, 94, 88, 80], [15, 48, 44, 44, 46, 32, 36, 12, 40, 42, 46]),
        2: ([80, 72, 90, 86, 100, 96, 112, 108, 124, 130, 136], [20, 14, 50, 12, 48, 14, 52, 12, 50, 45, 40]),
        3: ([110, 104, 114, 106, 113, 105, 112, 106, 113, 107, 110], [18, 18, 20, 17, 19, 18, 20, 17, 19, 18, 19]),
    }
    for col, (py, vol) in pola.items():
        harga = [200 - v for v in py]
        fig.add_trace(go.Scatter(x=xs, y=harga, mode="lines", line=dict(color=COL["cyan"], width=2.5)), 1, col)
        fig.add_hline(y=90, line=dict(color=COL["mute"], dash="dash", width=1), row=1, col=col)
        warna = [COL["mute"]] + [COL["green"] if harga[i] >= harga[i - 1] else COL["red"] for i in range(1, 11)]
        fig.add_trace(go.Bar(x=xs, y=vol, marker_color=warna), 2, col)
        fig.add_hline(y=30, line=dict(color=COL["amber"], dash="dot", width=1), row=2, col=col)
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)
    return gaya(fig, 420)


# =============================================================================
# 8. UI
# =============================================================================
st.set_page_config(page_title="Broker Map Board", page_icon="🗺️", layout="wide")
st.markdown("""<style>
.bm-h{font-family:monospace;color:#00ff9c;font-size:22px;font-weight:600;margin:0}
.bm-s{font-family:monospace;color:#7d8a99;font-size:12px}
.bm-card{border:1px solid #1b2430;border-radius:8px;padding:10px 12px;margin:6px 0;background:#0d1218;font-family:monospace}
</style>""", unsafe_allow_html=True)
now = datetime.now(WIB)
HARI = now.strftime("%Y-%m-%d")
st.markdown('<p class="bm-h">▌BROKER MAP BOARD</p>', unsafe_allow_html=True)
st.markdown(f'<p class="bm-s">Akun {S["akun"]} · {now.strftime("%a %d %b %Y %H:%M")} WIB · data harian '
            f'representatif setelah ±16.15</p>', unsafe_allow_html=True)
if ss.get("auto_src"):
    st.caption(f"State dimuat otomatis dari {ss['auto_src']}")

tabs = st.tabs(["AKSI", "SARINGAN", "PETA BROKER", "RENCANA", "JURNAL", "PANDUAN", "STATE"])

# ---------------------------------------------------------------- AKSI
with tabs[0]:
    ih = fetch_ihsg()
    c1, c2, c3, c4 = st.columns(4)
    if ih is not None and len(ih) > 21:
        ihc = float(ih["Close"].iloc[-1])
        c1.metric("IHSG", rp(ihc), f"{(ihc / float(ih['Close'].iloc[-21]) - 1) * 100:+.1f}% 20H")
    rugi_real = -sum(t.get("pl", 0) for t in S["log_transaksi"] if t.get("aksi") == "JUAL" and t.get("pl", 0) < 0)
    c2.metric("Anggaran rugi terpakai", jt(rugi_real), f"dari {jt(S['anggaran_rugi'])}", delta_color="off")
    c3.metric("Rencana aktif", sum(r.get("status") not in ("SELESAI", "BATAL") for r in S["rencana"]))
    c4.metric("Daftar pantau", len(S["pantau"]))
    st.markdown("#### Aksi per rencana")
    if not S["rencana"]:
        st.info("Belum ada rencana. Unggah state JSON di tab STATE.")
    for r in S["rencana"]:
        x = fetch_one(r["kode"])
        akt = evaluasi(r, x, HARI)
        if not akt:
            continue
        harga = rp(float(x["Close"].iloc[-1])) if x is not None else "-"
        tgl = x.index[-1].strftime("%d %b") if x is not None else "-"
        isi = "<br>".join(f"<b>{a}</b> · {t}" for a, t in akt)
        st.markdown(f'<div class="bm-card"><b>{r["kode"]}</b> · {r.get("status", "")} · tutup {harga} ({tgl})'
                    f' · batas {r.get("batas_waktu", "-")}<br>{isi}</div>', unsafe_allow_html=True)
    if S["pantau"]:
        st.markdown("#### Daftar pantau")
        rows = []
        for p in S["pantau"]:
            x = fetch_one(p["kode"])
            info = analisa(p["kode"], x)
            rows.append({"Kode": p["kode"], "Harga": info["Harga"] if info else None,
                         "Struktur": info["Struktur"] if info else "?",
                         "Val 09.30 (M)": info["Val 09.30 (M)"] if info else None,
                         "Batas bawah": p.get("batas_bawah"),
                         "Utuh?": (info["Harga"] >= p["batas_bawah"]) if info and p.get("batas_bawah") else None,
                         "Syarat": p.get("syarat", "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ---------------------------------------------------------------- SARINGAN
with tabs[1]:
    st.caption("Kriteria: range YTD < 40% · jarak support ≤ 1,5 ATR · stochastic < 20 / baru naik dari < 20 · "
               "naik 20 hari ≤ 20% dan pantulan dari low crash ≤ 3 ATR · value 20 hari > Rp5 M · "
               "SL 1,5 ATR + fee ≤ 10%. Struktur dari ZigZag 1 ATR.")
    if st.button("▶ PINDAI SEMUA EMITEN", width="stretch"):
        with st.spinner(f"Menarik {len(TICKERS)} emiten..."):
            data = fetch_all(TICKERS)
        rows = [r for r in (analisa(t, data.get(t)) for t in TICKERS) if r]
        ss["scan"] = rows
        ss["scan_n"] = len(data)
    if ss.get("scan"):
        rows = ss["scan"]
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_kri"} for r in rows])
        tgl_akhir = df["Tanggal"].max()
        df_now = df[df["Tanggal"] == tgl_akhir]
        lik = df_now[df_now["Val 20H (M)"] > VAL_MIN / 1e9]
        chart5 = [r for r in rows if r["Tanggal"] == tgl_akhir and all(v for k, v in r["_kri"].items()
                                                                       if k != "SL≤10%")]
        vol_ok = [r for r in chart5 if r["_kri"]["SL≤10%"]]
        bersih = [r for r in vol_ok if not kecuali_aktif(r["Kode"], HARI)]
        st_ok = [r for r in bersih if r["Struktur"] in ("HL", "CHOCH")]
        tahap = ["Universe", "Ada data", "Likuid", "Lolos 5 chart", "SL ≤ 10%", "Bukan kecuali", "Struktur HL/CHoCH"]
        nilai = [len(TICKERS), ss.get("scan_n", 0), len(lik), len(chart5), len(vol_ok), len(bersih), len(st_ok)]
        fig = go.Figure(go.Bar(x=tahap, y=nilai, marker_color=COL["cyan"], text=nilai, textposition="outside"))
        fig.update_yaxes(type="log")
        st.plotly_chart(gaya(fig, 300, f"Corong saringan · data {tgl_akhir}"), width="stretch")
        st.markdown("#### Kandidat (lolos semua + bukan kecuali)")
        kand = pd.DataFrame([{k: v for k, v in r.items() if k != "_kri"} for r in bersih])
        if len(kand):
            urut = {"CHOCH": 0, "HL": 1, "BELUM": 2, "RUSAK": 3, "?": 4}
            kand["_u"] = kand["Struktur"].map(urut).fillna(5)
            kand = kand.sort_values(["_u", "Val 20H (M)"], ascending=[True, False]).drop(columns="_u")
            st.dataframe(kand.drop(columns=["Lolos", "Tanggal"]), hide_index=True, width="stretch")
            st.plotly_chart(chart_bar(list(kand["Kode"]), list(kand["Pantul xATR"]),
                                      "Pantulan dari low crash (x ATR)", [COL["cyan"]] * len(kand)), width="stretch")
            if kand["Data curiga"].any():
                st.warning("Ada data curiga (gap > 16% atau harga pecahan): cocokkan ATR dengan Stockbit sebelum dipakai.")
        else:
            st.info("Tidak ada kandidat yang lolos semua saringan hari ini.")
        dicoret = [(r["Kode"], kecuali_aktif(r["Kode"], HARI)) for r in vol_ok if kecuali_aktif(r["Kode"], HARI)]
        if dicoret:
            st.caption("Dicoret karena daftar kecuali / red flag: " +
                       " · ".join(f"{k} ({a})" for k, a in dicoret))

        st.markdown("#### Cek berita & asing (BEI → RSS)")
        if len(kand):
            pilih = st.multiselect("Kandidat yang dicek", list(kand["Kode"]), default=list(kand["Kode"])[:10])
            if st.button("Cek berita kandidat"):
                for k in pilih:
                    sumber, hasil, dibuang = cek_berita(k)
                    ket = f" · {dibuang} judul umum dibuang" if dibuang else ""
                    if sumber == "GAGAL":
                        st.markdown(f"**{k}** · sumber berita gagal diakses")
                    elif not hasil:
                        st.markdown(f"**{k}** · {sumber}: ✅ tidak ada judul bertanda yang menyebut {k}{ket}")
                    else:
                        st.markdown(f"**{k}** · {sumber}: ⚠️ {len(hasil)} judul menyebut {k}{ket}")
                        st.dataframe(pd.DataFrame(hasil)[["tanggal", "tanda", "judul", "link"]],
                                     hide_index=True, width="stretch",
                                     column_config={"link": st.column_config.LinkColumn("link", display_text="buka")})
            if st.button("Ambil net asing harian dari BEI"):
                ok = None
                for mundur in range(0, 6):
                    tg = (now - timedelta(days=mundur)).strftime("%Y%m%d")
                    df_idx, pesan = idx_stock_summary(tg)
                    if df_idx is not None:
                        ok = (tg, df_idx)
                        break
                if ok:
                    tg, df_idx = ok
                    sub = df_idx.reindex([k for k in kand["Kode"]])
                    st.caption(f"Sumber BEI tanggal {tg}. Nilai Rp = net lembar × harga tutup (perkiraan).")
                    st.dataframe(sub.reset_index(), hide_index=True, width="stretch")
                else:
                    st.warning(f"Data BEI tidak bisa diakses ({pesan}). Pakai daftar asing dari saringan malam 20.30.")

# ---------------------------------------------------------------- PETA BROKER
with tabs[2]:
    pb = S["peta_broker"]
    if not pb:
        st.info("Belum ada peta broker. Kirim screenshot ke Claude, lalu unggah JSON yang diperbarui.")
    else:
        kode = st.selectbox("Saham", sorted(pb.keys()))
        e = pb[kode]
        x = fetch_one(kode)
        harga = float(x["Close"].iloc[-1]) if x is not None else e.get("harga_ref")
        st.markdown(f'<div class="bm-card"><b>{kode}</b> · data broker {e.get("tanggal", "-")} · harga ref '
                    f'{rp(e.get("harga_ref"))} · harga kini {rp(harga)}<br>Kriteria 7: <b>{e.get("kriteria7", "-")}</b>'
                    f' · status {e.get("status", "-")}<br>{e.get("catatan", "")}</div>', unsafe_allow_html=True)
        for per in ["1M", "1W"]:
            beli, jual = e.get(f"pembeli_{per}", []), e.get(f"penjual_{per}", [])
            if not beli and not jual:
                continue
            st.markdown(f"**Broker Summary {per} (Regular)**")
            cA, cB = st.columns(2)
            if beli:
                db = pd.DataFrame(beli)
                db["vs harga %"] = ((db["avg"] / harga - 1) * 100).round(1)
                db["ritel"] = db["kode"].isin(RITEL)
                cA.dataframe(db, hide_index=True, width="stretch")
            if jual:
                cB.dataframe(pd.DataFrame(jual), hide_index=True, width="stretch")
            if beli:
                lab = [f"{b['kode']} {per}" for b in beli[:3]]
                val = [round((b["avg"] / harga - 1) * 100, 1) for b in beli[:3]]
                st.plotly_chart(chart_bar(lab, val, f"Avg pembeli vs harga kini (%) · {per}",
                                          [COL["amber"] if abs(v) <= 5 else COL["red"] for v in val], 260),
                                width="stretch")
        if e.get("foreign_1M"):
            st.markdown("**Versi Foreign 1M**")
            st.dataframe(pd.DataFrame(e["foreign_1M"]), hide_index=True, width="stretch")
        if e.get("trade_flow"):
            st.markdown(f"**Trade Flow**: {e['trade_flow']}")

# ---------------------------------------------------------------- RENCANA
with tabs[3]:
    pilihan = [r["kode"] for r in S["rencana"]] + [p["kode"] for p in S["pantau"]]
    if not pilihan:
        st.info("Belum ada rencana atau daftar pantau.")
    else:
        kode = st.selectbox("Rencana / pantau", pilihan, key="sel_rencana")
        r = next((q for q in S["rencana"] if q["kode"] == kode), None)
        x = fetch_one(kode)
        if x is None:
            st.error("Data harga tidak tersedia.")
        else:
            h, l, c = (x[k].values.astype(float) for k in ["High", "Low", "Close"])
            s = struktur(h, l, c, atr_wilder(h, l, c))
            info = analisa(kode, x)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tutup", rp(c[-1]), x.index[-1].strftime("%d %b"))
            m2.metric("Struktur", s["status"])
            m3.metric("ATR14", rp(info["ATR"], 1) if info else "-")
            m4.metric("Val 09.30 OK ≥", f"Rp{rp(info['Val 09.30 (M)'], 1)} M" if info else "-")
            st.caption(f"ZigZag 1 ATR: sweep {rp(s['sweep'])} · HL {rp(s['hl'])} · CHoCH {rp(s['choch'])}. "
                       "Level di rencana (kalau ada) yang dipakai untuk aksi.")
            st.plotly_chart(chart_struktur(x, r, s), width="stretch")
            if r:
                hasil = hitung_rr([(e["harga"], e["lot"]) for e in r["entry"]],
                                  [(t["harga"], t["porsi"]) for t in r["tp"]], r["sl"])
                pertama = hitung_rr([(r["entry"][0]["harga"], r["entry"][0]["lot"])],
                                    [(t["harga"], t["porsi"]) for t in r["tp"]], r["sl"])
                skenario = [("Tahap 1 saja", pertama), ("Semua tahap", hasil)] if len(r["entry"]) > 1 else \
                    [("Semua tahap", hasil)]
                rows = []
                for nama, hs in skenario:
                    rows.append({"Skenario": nama, "Lot": hs["lot"], "Avg": round(hs["avg"]),
                                 "Lot TP": " / ".join(str(d["lot"]) for d in hs["per_tp"]),
                                 "Rugi SL": jt(hs["rugi"]), "Untung piramida": jt(hs["untung"]),
                                 "RR bersih": round(hs["rr"], 2)})
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                lab = [f"TP{i + 1}" for i in range(len(hasil["per_tp"]))] + ["Piramida"]
                val = [round(d["rr"], 2) for d in hasil["per_tp"]] + [round(hasil["rr"], 2)]
                st.plotly_chart(chart_bar(lab, val, "RR bersih fee + materai (semua tahap)",
                                          [COL["cyan"]] * len(val), 280), width="stretch")
                st.markdown(f'<div class="bm-card">Alasan: {r.get("alasan", "-")}<br>Keluar dini: '
                            f'{r.get("keluar_dini", "-")}<br>Pre-open: {r.get("aturan_preopen", "-")}</div>',
                            unsafe_allow_html=True)
            else:
                p = next((q for q in S["pantau"] if q["kode"] == kode), {})
                st.markdown(f'<div class="bm-card">Pantau · syarat: {p.get("syarat", "-")}</div>',
                            unsafe_allow_html=True)

# ---------------------------------------------------------------- JURNAL
with tabs[4]:
    st.markdown("#### Catat transaksi")
    with st.form("form_trx", clear_on_submit=True):
        f1, f2, f3, f4, f5 = st.columns(5)
        t_tgl = f1.date_input("Tanggal", now.date())
        t_kode = f2.text_input("Kode").strip().upper()
        t_aksi = f3.selectbox("Aksi", ["BELI", "JUAL"])
        t_lot = f4.number_input("Lot", 1, 100000, 1)
        t_harga = f5.number_input("Harga", 1, 1_000_000, 1000)
        t_ket = st.text_input("Keterangan (mis. tahap 1, TP1, SL, batas waktu)")
        kirim = st.form_submit_button("Simpan transaksi")
    if kirim and t_kode:
        nilai = t_lot * 100 * t_harga
        mat = materai(nilai)
        r = next((q for q in S["rencana"] if q["kode"] == t_kode and q.get("status") not in ("SELESAI", "BATAL")),
                 None)
        pl = None
        if t_aksi == "BELI":
            fee = nilai * FEE_BELI
            if r is not None:
                r.setdefault("terisi", []).append(dict(tanggal=str(t_tgl), harga=t_harga, lot=t_lot,
                                                       biaya=nilai + fee + mat))
                r["status"] = "POSISI"
        else:
            fee = nilai * FEE_JUAL
            if r is not None and r.get("terisi"):
                lot_isi = sum(e["lot"] for e in r["terisi"])
                biaya_per_lot = sum(e["biaya"] for e in r["terisi"]) / lot_isi
                pl = nilai - fee - mat - biaya_per_lot * t_lot
                r.setdefault("terjual", []).append(dict(tanggal=str(t_tgl), harga=t_harga, lot=t_lot,
                                                        alasan=t_ket, pl=round(pl)))
                if lot_pegang(r) <= 0:
                    r["status"] = "SELESAI"
        S["log_transaksi"].append(dict(tanggal=str(t_tgl), kode=t_kode, aksi=t_aksi, lot=t_lot, harga=t_harga,
                                       fee=round(fee), materai=mat, pl=round(pl) if pl is not None else None,
                                       ket=t_ket))
        st.success(f"Tersimpan: {t_aksi} {t_kode} {t_lot} lot @{rp(t_harga)} · fee {rp(fee)} · materai {rp(mat)}"
                   + (f" · P/L {rp(pl)}" if pl is not None else ""))
    log = pd.DataFrame(S["log_transaksi"])
    if len(log):
        st.dataframe(log, hide_index=True, width="stretch")
        jual = log[(log["aksi"] == "JUAL") & log["pl"].notna()]
        if len(jual):
            tot = float(jual["pl"].sum())
            st.metric("P/L realized", jt(tot))
            st.plotly_chart(chart_bar([f"{a} {b}" for a, b in zip(jual["kode"], jual["tanggal"])],
                                      list(jual["pl"] / 1e6), "P/L per penjualan (Rp jt)"), width="stretch")
    rugi = -sum(t.get("pl") or 0 for t in S["log_transaksi"] if (t.get("pl") or 0) < 0)
    sisa = S["anggaran_rugi"] - rugi
    st.plotly_chart(chart_bar(["Terpakai", "Sisa"], [rugi / 1e6, sisa / 1e6], "Anggaran rugi (Rp jt)",
                              [COL["red"], COL["green"]], 260), width="stretch")

# ---------------------------------------------------------------- PANDUAN
with tabs[5]:
    st.markdown("#### Chart 1 menit, jam 09.00–09.30")
    st.plotly_chart(chart_panduan(), width="stretch")
    st.markdown("""
- **Akumulasi**: batang merah besar (di atas garis oranye = 2× rata-rata volume) langsung diikuti naik; low makin tinggi.
- **Distribusi**: batang merah besar membuat low baru; naiknya kecil dengan batang hijau kecil.
- **Netral**: semua batang di bawah 2× rata-rata.
- Hitung jam 09.30: batang besar hijau > merah **dan** low tidak tembus level bawah → lanjut. Sebaliknya → batal.
- Abaikan stochastic & ATR 1 menit (noise). Val di header orderbook dibandingkan dengan patokan di bawah.
""")
    kode_v = [r["kode"] for r in S["rencana"]] + [p["kode"] for p in S["pantau"]]
    if kode_v:
        rows = []
        for k in kode_v:
            info = analisa(k, fetch_one(k))
            if info:
                rows.append({"Kode": k, "Val 20H (M)": info["Val 20H (M)"], "Val 09.30 OK ≥ (M)": info["Val 09.30 (M)"],
                             "Lot/menit 2× rata-rata ≈": round(info["Val 20H (M)"] * 1e9 / info["Harga"] / 100 / 290 * 2)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Patokan 20% dan 290 menit bursa adalah perkiraan awal; kalibrasi ulang setelah seminggu catatan.")

# ---------------------------------------------------------------- STATE
with tabs[6]:
    up = st.file_uploader("Unggah state (state_broker_map_*.json)", type="json")
    if up is not None and ss.get("_up") != (up.name, up.size):
        try:
            ss["state"] = muat_state(json.loads(up.getvalue().decode("utf-8")))
            ss["_up"] = (up.name, up.size)
            st.success(f"State dimuat dari {up.name}")
            st.rerun()
        except Exception as ex:
            st.error(f"JSON tidak valid: {ex}")
    S["disimpan"] = now.strftime("%Y-%m-%d %H:%M")
    st.download_button("Unduh state JSON", json.dumps(S, indent=2, ensure_ascii=False, default=str),
                       file_name=f"state_broker_map_{HARI}.json", mime="application/json", width="stretch")
    st.markdown("**Daftar kecuali aktif**")
    kc = [{"Kode": k, "Alasan": v.get("alasan"), "Sampai": v.get("sampai")} for k, v in S["kecuali"].items()]
    if kc:
        st.dataframe(pd.DataFrame(kc), hide_index=True, width="stretch")
    st.caption(f"Red flag tetap: {' '.join(sorted(RED_FLAG))}")
