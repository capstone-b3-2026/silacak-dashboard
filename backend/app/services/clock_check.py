"""Deteksi jam laptop yang tidak sinkron dengan jam GPS pendaki (fungsi MURNI).

Latensi = received_at (jam laptop saat paket masuk DB) - recorded_at (jam GPS pendaki). Kalau jam laptop tertinggal, latensi
terlihat NEGATIF padahal paket pasti sampai sesudah dikirim. Tanpa internet (di basecamp) jam Windows bisa melenceng jauh.

Aturan yang dipakai dan batasnya:
- recorded_at dari GPS berresolusi 1 detik dan dipotong ke bawah, jadi latensi terukur selalu >= latensi sebenarnya (> 0).
  Karena itu NILAI MINIMUM yang sangat negatif hanya bisa berarti jam laptop tertinggal; toleransi 0,5 dtk untuk galat jam.
- Selisih jam yang lebih BESAR dari latensi nyata tidak bisa dibedakan dari "paket memang telat" bila jam laptop MAJU.
  Minimum latensi > 60 dtk hanya dilaporkan sebagai curiga, bukan diagnosis.
- Fungsi ini hanya MENDETEKSI dan memperkirakan selisih; mengubah jam Windows butuh hak admin dan di luar aplikasi ini.
"""
from __future__ import annotations

import statistics

MIN_SAMPLES = 5
BEHIND_TOL_S = 0.5      # min latensi di bawah -0,5 dtk = jam laptop tertinggal
SUSPECT_MIN_S = 60.0    # min latensi di atas ini = jam laptop maju ATAU latensi jaringan sangat besar


def assess(latencies_s) -> dict:
    vals = [float(v) for v in latencies_s if v is not None]
    n = len(vals)
    if n < MIN_SAMPLES:
        return {"status": "belum_cukup_data", "n": n, "message": f"Butuh minimal {MIN_SAMPLES} paket berjam GPS untuk menilai jam laptop."}
    mn, med = min(vals), statistics.median(vals)
    neg = sum(1 for v in vals if v < 0)
    out = {"n": n, "min_s": round(mn, 2), "median_s": round(med, 2), "negatif_persen": round(100.0 * neg / n, 1),
           "offset_perkiraan_s": 0.0}
    if mn < -BEHIND_TOL_S:
        out.update(status="jam_laptop_tertinggal", offset_perkiraan_s=round(-mn, 2),
                   message=f"Jam laptop tertinggal sedikitnya {-mn:.1f} dtk dari jam GPS (latensi negatif). Latensi yang tampil tidak "
                           "bisa dipercaya sampai jam Windows disinkronkan.")
    elif mn > SUSPECT_MIN_S:
        out.update(status="curiga_jam_maju",
                   message=f"Paket tercepat pun tampak {mn:.0f} dtk lebih lambat dari jam GPS: jam laptop mungkin maju, atau "
                           "memang ada tundaan besar. Periksa jam laptop.")
    else:
        out.update(status="ok", message="Jam laptop selaras dengan jam GPS dalam batas pengukuran.")
    return out
