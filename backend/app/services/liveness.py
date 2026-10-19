"""Kapan pendaki dianggap 'tidak terdengar' (node basi).

Interval kirim TIDAK boleh diasumsikan: firmware `pendaki_optimized` mengirim terus-menerus
(jeda ~300 ms), `pendaki_real` tiap 5 s +-20% (+ coba-ulang cepat), dan angka 30 s di C-251 tidak
ada di kode firmware. Jadi ambangnya DIUKUR dari paket yang benar-benar diterima:

    ambang = K x median(jeda antar paket terbaru), dibatasi [MIN_S, MAX_S]

Median dipilih karena kebal terhadap sesekali jeda panjang (blackout) maupun coba-ulang cepat.
Kalau paketnya belum cukup untuk diukur, pakai interval yang dikonfigurasi (kalau ada).
"""
from __future__ import annotations

from statistics import median

K = 4.0               # toleransi: 4x jeda tipikal (sama dengan asumsi lama 120 s = 4 x 30 s)
MIN_S = 15.0          # batas bawah: mode 'optimized' (jeda sub-detik) tidak boleh bikin status berkedip
MAX_S = 600.0
FALLBACK_S = 120.0    # tidak ada data & tidak ada konfigurasi
MIN_GAPS = 3          # minimal 3 jeda (4 paket) baru dianggap terukur


def observed_interval_s(received_epochs_desc: list[float] | None) -> float | None:
    """Median jeda antar paket. Input: waktu terima (epoch detik), terbaru dulu."""
    if not received_epochs_desc or len(received_epochs_desc) < MIN_GAPS + 1:
        return None
    ts = received_epochs_desc
    gaps = [a - b for a, b in zip(ts, ts[1:]) if a - b > 0]
    if len(gaps) < MIN_GAPS:
        return None
    return float(median(gaps))


def stale_threshold_s(received_epochs_desc: list[float] | None, configured_interval_s: float | None = None) -> float:
    iv = observed_interval_s(received_epochs_desc)
    if iv is None and configured_interval_s:
        iv = float(configured_interval_s)
    if iv is None:
        return FALLBACK_S
    return max(MIN_S, min(MAX_S, K * iv))
