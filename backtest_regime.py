"""
backtest_regime.py
Modul fondasi Regime Screener: deteksi fase IHSG (BEAR / BOTTOM-REBOUND / NORMALIZING)
dan backtest probabilitas historis + Maximum Adverse Excursion (MAE) untuk manajemen risiko.

Sumber data: Yahoo Finance (^JKSE), tanpa biaya, historis sejak 2000.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Konfigurasi (angka-angka ini yang boleh dikalibrasi ulang nanti)
# ---------------------------------------------------------------------------
BEAR_THRESHOLD = -0.20          # drawdown dari puncak rolling 52w untuk masuk fase BEAR
REBOUND_TRIGGER = 0.20          # kenaikan dari trough untuk anggap BOTTOM-REBOUND terkonfirmasi
NORMALIZING_TRIGGER = 0.20      # kenaikan dari trough untuk anggap sudah masuk NORMALIZING (sama angka,
                                 # dipisah biar gampang dikalibrasi beda kalau perlu nanti)
MIN_EPISODE_DAYS = 20           # minimal panjang episode bear (hari kalender) supaya bukan noise
MERGE_GAP_DAYS = 90             # gabungkan dua periode bear kalau jaraknya < ini (hindari pecah episode sama)
FORWARD_HORIZONS = [20, 40, 60, 120]   # hari bursa, dipakai buat hitung forward return & MAE


@dataclass
class RegimeEpisode:
    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    drawdown_pct: float
    signal_date: pd.Timestamp          # tanggal saat rebound 20% dari trough terkonfirmasi
    signal_price: float
    forward_returns: dict = field(default_factory=dict)   # {horizon: return %}
    mae: dict = field(default_factory=dict)                # {horizon: (mae %, hari ke-berapa)}
    is_ongoing: bool = False            # True kalau episode ini belum selesai (data belum cukup ke depan)


def fetch_ihsg(start="2000-01-01") -> pd.Series:
    """Ambil data close harian IHSG dari Yahoo Finance."""
    df = yf.download("^JKSE", start=start, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def find_bear_episodes(close: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Cari periode-periode drawdown >= BEAR_THRESHOLD dari puncak rolling 252 hari."""
    roll_max = close.rolling(252, min_periods=50).max()
    drawdown = (close - roll_max) / roll_max
    in_bear = drawdown <= BEAR_THRESHOLD

    raw = []
    start = None
    for date, flag in in_bear.items():
        if flag and start is None:
            start = date
        if not flag and start is not None:
            raw.append((start, date))
            start = None
    if start is not None:
        raw.append((start, in_bear.index[-1]))

    merged = []
    for s, e in raw:
        if merged and (s - merged[-1][1]).days < MERGE_GAP_DAYS:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    return [(s, e) for s, e in merged if (e - s).days >= MIN_EPISODE_DAYS]


def build_episodes(close: pd.Series) -> list[RegimeEpisode]:
    """Untuk tiap episode bear, cari titik sinyal (rebound 20% dari trough), lalu hitung
    forward return dan MAE di tiap horizon. Episode yang belum cukup data ke depan ditandai ongoing."""
    episodes = []
    for peak_date, episode_end in find_bear_episodes(close):
        seg = close[peak_date:episode_end]
        trough_date = seg.idxmin()
        trough_price = seg.min()
        peak_price = close.rolling(252, min_periods=50).max()[peak_date]
        drawdown_pct = (trough_price - peak_price) / peak_price * 100

        target = trough_price * (1 + REBOUND_TRIGGER)
        after_trough = close[trough_date:]
        hit = after_trough[after_trough >= target]
        if len(hit) == 0:
            continue  # belum pernah rebound 20%, skip (kasusnya nggak akan terjadi kalau episode sudah "selesai")

        signal_date = hit.index[0]
        signal_price = hit.iloc[0]

        ep = RegimeEpisode(peak_date, trough_date, drawdown_pct, signal_date, signal_price)

        future = close[close.index > signal_date]
        if len(future) < FORWARD_HORIZONS[0]:
            ep.is_ongoing = True
            episodes.append(ep)
            continue

        for h in FORWARD_HORIZONS:
            if len(future) >= h:
                fwd_price = future.iloc[h - 1]
                ep.forward_returns[h] = round((fwd_price - signal_price) / signal_price * 100, 2)
                window = future.iloc[:h]
                min_price = window.min()
                min_day = int(window.values.argmin()) + 1
                ep.mae[h] = (round((min_price - signal_price) / signal_price * 100, 2), min_day)
            else:
                ep.is_ongoing = True  # horizon terpanjang belum tercapai -> tandai ongoing juga

        episodes.append(ep)
    return episodes


def summarize(episodes: list[RegimeEpisode]) -> pd.DataFrame:
    """Ringkas statistik forward return & MAE lintas semua episode yang SUDAH selesai
    (episode ongoing / current dikeluarkan dari statistik, ditampilkan terpisah)."""
    completed = [e for e in episodes if not e.is_ongoing]
    rows = []
    for h in FORWARD_HORIZONS:
        rets = [e.forward_returns[h] for e in completed if h in e.forward_returns]
        maes = [e.mae[h][0] for e in completed if h in e.mae]
        if not rets:
            continue
        rows.append({
            "horizon_hari": h,
            "n_sampel": len(rets),
            "rata_rata_return_%": round(np.mean(rets), 1),
            "pct_positif": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 0),
            "worst_return_%": round(min(rets), 1),
            "best_return_%": round(max(rets), 1),
            "rata_rata_MAE_%": round(np.mean(maes), 1),
            "worst_MAE_%": round(min(maes), 1),
        })
    return pd.DataFrame(rows)


def current_status(close: pd.Series, episodes: list[RegimeEpisode]) -> dict:
    """Fase pasar saat ini + posisi harga terakhir relatif terhadap trough terakhir."""
    last_price = close.iloc[-1]
    last_date = close.index[-1]
    roll_max = close.rolling(252, min_periods=50).max()
    dd_now = (last_price - roll_max.iloc[-1]) / roll_max.iloc[-1] * 100

    ongoing = [e for e in episodes if e.is_ongoing]
    status = {
        "tanggal": last_date.date(),
        "harga": round(last_price, 2),
        "drawdown_dari_puncak_52w_%": round(dd_now, 1),
    }
    if ongoing:
        ep = ongoing[-1]
        pct_from_trough = (last_price - close[ep.trough_date]) / close[ep.trough_date] * 100
        if pct_from_trough >= NORMALIZING_TRIGGER * 100:
            fase = "NORMALIZING"
        elif pct_from_trough >= REBOUND_TRIGGER * 100:
            fase = "BOTTOM-REBOUND (terkonfirmasi)"
        else:
            fase = "BEAR (belum rebound 20%)"
        status.update({
            "fase": fase,
            "trough_terakhir": (ep.trough_date.date(), round(close[ep.trough_date], 2)),
            "pct_dari_trough_%": round(pct_from_trough, 1),
        })
    else:
        status["fase"] = "NORMAL (tidak dalam bear market >=20%)"
    return status


if __name__ == "__main__":
    close = fetch_ihsg()
    episodes = build_episodes(close)
    summary = summarize(episodes)
    status = current_status(close, episodes)

    print("=== STATUS SAAT INI ===")
    for k, v in status.items():
        print(f"{k}: {v}")

    print("\n=== RINGKASAN BACKTEST (episode selesai, n={}) ===".format(
        len([e for e in episodes if not e.is_ongoing])))
    print(summary.to_string(index=False))

    print("\n=== DETAIL TIAP EPISODE ===")
    for e in episodes:
        tag = " (ONGOING/SEKARANG)" if e.is_ongoing else ""
        print(f"\nPuncak {e.peak_date.date()} -> Trough {e.trough_date.date()} "
              f"(drawdown {e.drawdown_pct:.1f}%) -> Sinyal {e.signal_date.date()} @ {e.signal_price:.0f}{tag}")
        for h in FORWARD_HORIZONS:
            if h in e.forward_returns:
                mae_val, mae_day = e.mae[h]
                print(f"  +{h}h: return {e.forward_returns[h]:+.1f}%, MAE {mae_val:.1f}% (hari ke-{mae_day})")
