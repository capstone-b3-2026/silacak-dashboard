"""Kalibrasi model tautan dari RSSI lapangan (fungsi MURNI, tanpa DB/FastAPI).

Idenya: perencana memprediksi RSSI tiap link (anggaran daya + medan + vegetasi). Setelah ada paket
nyata, bandingkan RSSI terukur dengan prediksi pada posisi yang sama:

    residu = RSSI_terukur - RSSI_prediksi        (negatif = kenyataan lebih lemah dari model)
    offset_baru = offset_lama - median(residu)   (redaman tambahan yang membuat model cocok dengan lapangan)
    fade_margin = 1.28 * sigma(residu)           (sekitar 90% paket di atas ambang; z = 1.28)

Peringatan statistik yang HARUS dipahami:
  - Bias sensor: hanya paket yang BERHASIL diterima yang punya RSSI. Di tepi jangkauan, paket lemah
    hilang sehingga residu terlihat lebih bagus daripada kenyataan (censoring). Kalibrasi pada jarak
    di mana PDR masih tinggi (batasi dengan max_km), jangan di tepi jangkauan.
  - Satu offset konstan tidak bisa memperbaiki eksponen redaman yang salah. `resid_slope_db_per_decade`
    menunjukkan apakah residu berubah terhadap jarak; kalau besar, offset saja tidak cukup.
  - `rssi_p01_dbm` (RSSI terendah yang masih diterima) adalah batas atas sensitivitas efektif: sensitivitas
    sebenarnya tidak mungkin lebih baik dari itu. Bandingkan dengan parameter sensitivitas perencana.
"""

from __future__ import annotations

import numpy as np


def calibrate(
    measured_dbm,
    predicted_dbm,
    dist_km,
    *,
    current_offset_db: float = 0.0,
    min_points: int = 30,
    min_dist_ratio: float = 2.0,
    z: float = 1.28,
) -> dict:
    m = np.asarray(measured_dbm, dtype=float)
    p = np.asarray(predicted_dbm, dtype=float)
    d = np.asarray(dist_km, dtype=float)
    ok = np.isfinite(m) & np.isfinite(p) & np.isfinite(d) & (d > 0)
    m, p, d = m[ok], p[ok], d[ok]
    n = int(m.size)
    out: dict = {"n": n, "current_offset_db": round(float(current_offset_db), 1), "reliable": False, "problems": []}
    if n == 0:
        out["problems"].append("Tidak ada paket langsung (0 hop) berposisi valid pada rentang ini.")
        return out

    resid = m - p
    bias_mean = float(resid.mean())
    bias_med = float(np.median(resid))
    sigma = float(resid.std(ddof=1)) if n > 1 else float("nan")
    p10, p90 = float(np.percentile(d, 10)), float(np.percentile(d, 90))
    ratio = p90 / p10 if p10 > 0 else float("inf")
    slope = None
    if n >= 5 and ratio > 1.2:
        slope = float(np.polyfit(np.log10(d), resid, 1)[0])  # dB per dekade jarak

    out.update({
        "bias_mean_db": round(bias_mean, 1), "bias_median_db": round(bias_med, 1),
        "sigma_db": None if not np.isfinite(sigma) else round(sigma, 1),
        "resid_slope_db_per_decade": None if slope is None else round(slope, 1),
        "dist_p10_km": round(p10, 3), "dist_p90_km": round(p90, 3),
        "rssi_p01_dbm": round(float(np.percentile(m, 1)), 1), "rssi_min_dbm": round(float(m.min()), 1),
        "suggested_calib_offset_db": round(float(current_offset_db) - bias_med, 1),
        "suggested_fade_margin_db": None if not np.isfinite(sigma) else round(float(np.clip(z * sigma, 3.0, 20.0)) * 2) / 2,
    })
    if n < min_points:
        out["problems"].append(f"Data kurang: {n} paket (minimal {min_points}).")
    if ratio < min_dist_ratio:
        out["problems"].append(
            f"Rentang jarak sempit (P90/P10 = {ratio:.1f}, minimal {min_dist_ratio:.1f}): offset bisa salah arah.")
    if slope is not None and abs(slope) > 8.0:
        out["problems"].append(
            f"Residu berubah {slope:+.0f} dB per dekade jarak: offset konstan tidak cukup "
            "(eksponen redaman lapangan beda dari model).")
    out["reliable"] = not any(s.startswith(("Data kurang", "Rentang jarak")) for s in out["problems"])
    return out