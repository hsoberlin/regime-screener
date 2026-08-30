"""
engine.py
Engine utama Regime Screener -- menggabungkan:
  Tahap 1: status fase IHSG (dari backtest_regime.py)
  Tahap 2: status sektor (return sejak bottom IHSG)
  Tahap 3: peringkat emiten (gerbang keras -> skor 100% -> tier -> modifier)
  Tahap 4: bobot ekuitas (aturan all-in/tie-breaker/cash ditahan/cash menganggur)

Output: JSON tunggal yang dikonsumsi dashboard.html.
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from backtest_regime import fetch_ihsg, build_episodes, current_status, summarize
from universe import SECTOR_BASKETS, SEKTOR_FINANSIAL, PAPAN_PENGEMBANGAN, ALL_TICKERS

# ---------------------------------------------------------------------------
# Parameter (semua angka yang disepakati sepanjang diskusi -- kalibrasi di sini)
# ---------------------------------------------------------------------------
PARTICIPATION_VOL_RATIO = 4.0        # "volume meledak" -- syarat eksekusi (opsi 1)
PARTICIPATION_VALUE_IDR = 100_000_000_000  # Rp100 miliar -- syarat eksekusi (opsi 2)
GAP_SIGNIFIKAN_THRESHOLD = -10.0     # gap vs sektor (%) minimal buat dianggap "laggard sungguhan"
BERAT_NAIK_DER_MULTIPLIER = 1.5      # DER > 1.5x median sektor -> kena penalti
BERAT_NAIK_BETA_THRESHOLD = 0.3      # |beta| < ini -> kena penalti (nyaris tidak bergerak)
BERAT_NAIK_TOP_N_MCAP = 2            # 2 saham terbesar sektor -> kena penalti
BERAT_NAIK_PENALTY = 0.5             # skor dikali ini kalau kena penalti (filter LUNAK)
DRAWDOWN_GATE_MULTIPLIER = 1.5       # max DD historis > 1.5x median sektor -> gerbang keras gagal
MODAL_EQUITAS = 20_000_000           # Rp20 juta, sesuai kesepakatan


def fetch_universe_data(tickers, lookback_days=400):
    raw = yf.download(tickers, period=f"{lookback_days}d", progress=False)
    return raw


def compute_sector_status(ohlcv, sector_baskets, ihsg_trough_date):
    """Tahap 2: return tiap sektor sejak trough IHSG terakhir, plus ranking."""
    close = ohlcv["Close"]
    results = []
    for sector, tickers in sector_baskets.items():
        rets = []
        for t in tickers:
            if t not in close.columns:
                continue
            s = close[t].dropna()
            s_after = s[s.index >= ihsg_trough_date]
            if len(s_after) < 2:
                continue
            r = (s_after.iloc[-1] - s_after.iloc[0]) / s_after.iloc[0] * 100
            rets.append(r)
        if rets:
            avg = float(np.mean(rets))
            results.append({"sektor": sector, "return_sejak_bottom_pct": round(avg, 1), "n_saham": len(rets)})
    results.sort(key=lambda x: -x["return_sejak_bottom_pct"])
    for i, r in enumerate(results):
        r["ranking"] = i + 1
        r["sudah_bergerak"] = r["return_sejak_bottom_pct"] > 0  # syarat dasar tahap 2
    return results


def compute_stock_metrics(ohlcv, ticker, sector_avg_return, ihsg_trough_date):
    """Hitung semua metrik mentah satu saham untuk tahap 3."""
    close = ohlcv["Close"][ticker].dropna() if ticker in ohlcv["Close"].columns else pd.Series(dtype=float)
    volume = ohlcv["Volume"][ticker].dropna() if ticker in ohlcv["Volume"].columns else pd.Series(dtype=float)
    if len(close) < 25 or len(volume) < 25:
        return None

    close_after = close[close.index >= ihsg_trough_date]
    if len(close_after) < 2:
        return None
    stock_return = (close_after.iloc[-1] - close_after.iloc[0]) / close_after.iloc[0] * 100
    gap_vs_sektor = stock_return - sector_avg_return

    vol_5h = volume.tail(5).mean()
    vol_20h = volume.tail(20).mean()
    vol_ratio_20h = vol_5h / vol_20h if vol_20h > 0 else 0
    vol_ratio_today = volume.iloc[-1] / vol_20h if vol_20h > 0 else 0

    low_recent = close.tail(5).min()
    low_prior = close.tail(40).head(20).min() if len(close) >= 40 else close.min()
    higher_low = low_recent > low_prior

    value_sesi_ini = close.iloc[-1] * volume.iloc[-1]  # proksi kasar (harga close x volume)

    roll_max_3y = close.rolling(min(len(close), 750), min_periods=50).max()
    dd_series = (close - roll_max_3y) / roll_max_3y * 100
    max_dd_3y = float(dd_series.min()) if not dd_series.isna().all() else 0.0

    return {
        "return_sejak_bottom_pct": round(stock_return, 1),
        "gap_vs_sektor_pct": round(gap_vs_sektor, 1),
        "vol_ratio_5h_20h": round(vol_ratio_20h, 2),
        "vol_ratio_today": round(vol_ratio_today, 2),
        "higher_low": bool(higher_low),
        "value_sesi_ini_idr": float(value_sesi_ini),
        "max_drawdown_3y_pct": round(max_dd_3y, 1),
        "harga_terakhir": float(close.iloc[-1]),
        "harga_20h": [round(float(p), 0) for p in close.tail(20).tolist()],
        "volume_20h": [int(v) for v in volume.tail(20).tolist()],
    }


def apply_hard_gates(ticker, metrics, sector_median_dd):
    """Gerbang keras -- gagal salah satu = tidak lolos ke skor sama sekali."""
    reasons = []
    if ticker in PAPAN_PENGEMBANGAN:
        reasons.append("Papan Pengembangan")
    if sector_median_dd != 0 and metrics["max_drawdown_3y_pct"] < sector_median_dd * DRAWDOWN_GATE_MULTIPLIER:
        reasons.append("drawdown historis ekstrem vs median sektor")
    return reasons


def compute_berat_naik_penalty(ticker, metrics, info, sector_tickers, sector_der_median, market_caps):
    """Filter LUNAK -- kena salah satu = skor dikali BERAT_NAIK_PENALTY."""
    reasons = []
    der = info.get("debtToEquity")
    beta = info.get("beta")
    mcap = info.get("marketCap")

    if der is not None and sector_der_median and sector_der_median > 0:
        if der > sector_der_median * BERAT_NAIK_DER_MULTIPLIER:
            reasons.append(f"DER {der:.0f} > {BERAT_NAIK_DER_MULTIPLIER}x median sektor")
    if beta is not None and abs(beta) < BERAT_NAIK_BETA_THRESHOLD:
        reasons.append(f"beta {beta:.2f} mendekati nol")
    if mcap is not None and market_caps:
        sorted_caps = sorted(market_caps.items(), key=lambda x: -x[1])
        top_n = {t for t, _ in sorted_caps[:BERAT_NAIK_TOP_N_MCAP]}
        if ticker in top_n:
            reasons.append(f"termasuk {BERAT_NAIK_TOP_N_MCAP} saham terbesar sektor")
    return reasons


def compute_score_and_tier(metrics, gate_reasons, penalty_reasons):
    if gate_reasons:
        return 0.0, "tidak_lolos_gerbang", gate_reasons

    gap = metrics["gap_vs_sektor_pct"]
    gap_score = max(0, min(100, (-gap) * 2)) if gap < 0 else 0  # makin negatif (tertinggal) makin tinggi skornya
    participation_score = 0
    if metrics["vol_ratio_5h_20h"] > 1.0:
        participation_score += 50
    if metrics["higher_low"]:
        participation_score += 50

    skor_inti = gap_score * 0.60 + participation_score * 0.40  # RSS (15%) belum ada data live -> dikeluarkan dari skor untuk v1, lihat catatan di README

    skor_final = skor_inti
    if penalty_reasons:
        skor_final *= BERAT_NAIK_PENALTY

    gap_signifikan = gap <= GAP_SIGNIFIKAN_THRESHOLD
    partisipasi_ok = metrics["vol_ratio_5h_20h"] > 1.0 and metrics["higher_low"]

    if gap_signifikan and partisipasi_ok:
        tier = "kandidat_kuat"
    elif gap_signifikan and not partisipasi_ok:
        tier = "menunggu_konfirmasi"
    else:
        tier = "gap_tidak_signifikan"

    return round(skor_final, 1), tier, []


def compute_equity_allocation(candidates):
    """Tahap 4: aturan bobot ekuitas Rp20 juta."""
    hijau = [c for c in candidates if c["tier"] == "kandidat_kuat"]
    if not hijau:
        return {"status": "cash_menganggur", "detail": "Tidak ada kandidat Tier hijau saat ini.", "alokasi": []}

    lolos_eksekusi = [
        c for c in hijau
        if c["metrics"]["value_sesi_ini_idr"] >= PARTICIPATION_VALUE_IDR
        or c["metrics"]["vol_ratio_today"] >= PARTICIPATION_VOL_RATIO
    ]
    if not lolos_eksekusi:
        return {
            "status": "cash_ditahan",
            "detail": f"Ada {len(hijau)} kandidat Tier hijau, tapi belum lolos ambang eksekusi (Value>=Rp100M atau Vol>=4x).",
            "alokasi": [],
            "kandidat_menunggu": [c["ticker"] for c in hijau],
        }

    if len(lolos_eksekusi) == 1:
        pilihan = lolos_eksekusi[0]
        alasan = "satu-satunya kandidat lolos eksekusi"
    else:
        tanpa_penalti = [c for c in lolos_eksekusi if not c["penalty_reasons"]]
        pool = tanpa_penalti if tanpa_penalti else lolos_eksekusi
        pilihan = max(pool, key=lambda c: c["metrics"]["vol_ratio_today"])
        kalah = [c["ticker"] for c in lolos_eksekusi if c["ticker"] != pilihan["ticker"]]
        alasan = f"menang tie-breaker (vol {pilihan['metrics']['vol_ratio_today']:.1f}x) vs {', '.join(kalah)}"

    return {
        "status": "all_in",
        "detail": alasan,
        "alokasi": [{"ticker": pilihan["ticker"], "modal_idr": MODAL_EQUITAS}],
        "kalah_tie_breaker": [c["ticker"] for c in lolos_eksekusi if c["ticker"] != pilihan["ticker"]],
    }


def run():
    print("Mengambil data IHSG...")
    ihsg_close = fetch_ihsg()
    episodes = build_episodes(ihsg_close)
    ihsg_status = current_status(ihsg_close, episodes)
    backtest_summary = summarize(episodes).to_dict("records")

    ongoing = [e for e in episodes if e.is_ongoing]
    trough_date = ongoing[-1].trough_date if ongoing else ihsg_close.index[-250]

    print("Mengambil data universe saham...")
    ohlcv = fetch_universe_data(ALL_TICKERS)

    print("Menghitung status sektor...")
    sector_status = compute_sector_status(ohlcv, SECTOR_BASKETS, trough_date)
    sector_return_map = {s["sektor"]: s["return_sejak_bottom_pct"] for s in sector_status}

    print("Menghitung metrik & skor tiap saham...")
    all_candidates = []
    for sector, tickers in SECTOR_BASKETS.items():
        sector_avg = sector_return_map.get(sector, 0)
        if sector_avg <= 0:
            continue  # syarat tahap 2: sektor belum bergerak -> skip semua saham di dalamnya

        infos = {}
        market_caps = {}
        der_values = []
        dd_values = []
        stock_metrics_map = {}
        for t in tickers:
            m = compute_stock_metrics(ohlcv, t, sector_avg, trough_date)
            if m is None:
                continue
            stock_metrics_map[t] = m
            dd_values.append(m["max_drawdown_3y_pct"])
            try:
                info = yf.Ticker(t).info
                infos[t] = info
                if info.get("marketCap"):
                    market_caps[t] = info["marketCap"]
                if sector not in SEKTOR_FINANSIAL and info.get("debtToEquity"):
                    der_values.append(info["debtToEquity"])
            except Exception:
                infos[t] = {}

        sector_median_dd = float(np.median(dd_values)) if dd_values else 0
        sector_der_median = float(np.median(der_values)) if der_values else None

        for t, m in stock_metrics_map.items():
            gate_reasons = apply_hard_gates(t, m, sector_median_dd)
            penalty_reasons = []
            if not gate_reasons and sector not in SEKTOR_FINANSIAL:
                penalty_reasons = compute_berat_naik_penalty(t, m, infos.get(t, {}), tickers, sector_der_median, market_caps)
            score, tier, _ = compute_score_and_tier(m, gate_reasons, penalty_reasons)
            all_candidates.append({
                "ticker": t.replace(".JK", ""),
                "sektor": sector,
                "skor": score,
                "tier": tier,
                "gate_reasons": gate_reasons,
                "penalty_reasons": penalty_reasons,
                "metrics": m,
            })

    print("Menghitung bobot ekuitas (Tahap 4)...")
    equity_allocation = compute_equity_allocation(all_candidates)

    output = {
        "generated_at": datetime.now().isoformat(),
        "ihsg": {**ihsg_status, "tanggal": str(ihsg_status["tanggal"])},
        "backtest_summary": backtest_summary,
        "sektor": sector_status,
        "kandidat": sorted(all_candidates, key=lambda c: -c["skor"]),
        "bobot_ekuitas": equity_allocation,
        "modal_equitas_idr": MODAL_EQUITAS,
    }

    with open("screener_output.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("Selesai -> screener_output.json")
    return output


if __name__ == "__main__":
    run()
