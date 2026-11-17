"""Putar ulang rekaman jalan (fix GPS) terhadap detektor alarm untuk menilai ALARM PALSU dan keterlambatan deteksi (fungsi MURNI).

Tujuan: kalibrasi ambang (lebar koridor, radius diam, jendela diam, debounce) memakai data lapangan nyata, bukan tebakan.
Rumusnya SAMA dengan detektor sungguhan, bukan perkiraan:
- OFF_TRAIL : geo.is_off_trail (jarak titik ke jalur, debounce N paket terbaru) seperti services/off_trail_watch.py.
- STAGNANT  : window dipilih geo.choose_window_minutes dari jarak posisi terakhir ke jalur, lalu logika SQL
              position_repo.find_stagnant_sessions ditiru: (a) SEMUA fix dalam window berjarak <= radius dari fix terakhir,
              (b) ada fix di 10 menit PERTAMA window. Kesesuaian dengan SQL asli diuji di tests/test_db_integration.py.

Cara menilai:
- Tanpa kebenaran dasar (truth): rekaman dianggap jalan NORMAL (termasuk istirahat); SETIAP alarm = alarm palsu.
- Dengan truth: selang waktu [mulai, selesai] saat alarm JENIS itu memang seharusnya menyala (mis. sengaja keluar jalur, atau
  berpura-pura celaka dan diam). Alarm di luar selang itu = alarm palsu; tiap selang diukur keterlambatan deteksinya.

Batas: ini mengukur ambang terhadap SATU rekaman. Kesimpulan yang sah butuh banyak rekaman (tutupan kanopi, cuaca, pola istirahat
berbeda). Hasil di data sintetis hanya membuktikan alatnya benar, bukan bahwa ambang tertentu aman di lapangan.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right

from app.services.geo import choose_window_minutes, dist_point_to_trail_m, haversine_m, is_off_trail

Fix = tuple  # (t_epoch_detik, lat, lon), terurut menaik menurut t


def stagnant_at(fixes: list[Fix], t: float, window_min: float, radius_m: float) -> bool:
    """Apakah pendaki 'diam' pada waktu t menurut aturan find_stagnant_sessions. fixes harus terurut menurut waktu."""
    times = [f[0] for f in fixes]
    hi = bisect_right(times, t)
    if hi == 0:
        return False
    last = fixes[hi - 1]
    w = window_min * 60.0
    lo = bisect_left(times, t - w)
    inwin = fixes[lo:hi]
    if any(haversine_m(f[1], f[2], last[1], last[2]) > radius_m for f in inwin):
        return False
    first10 = bisect_right(times, t - w + 600.0)       # fix di [t-w, t-w+10 menit]
    return first10 > lo


def replay_off_trail(fixes: list[Fix], trail, perimeter_m: float, debounce_n: int) -> list[tuple]:
    """[(t, alarm_menyala)] di tiap fix. trail = [(lat, lon), ...]."""
    out = []
    for i, f in enumerate(fixes):
        recent = [(g[1], g[2]) for g in reversed(fixes[max(0, i - debounce_n + 1): i + 1])]  # terbaru dulu
        out.append((f[0], bool(is_off_trail(recent, trail, perimeter_m, debounce_n))))
    return out


def replay_stagnant(fixes: list[Fix], trail, perimeter_m: float, radius_m: float, inside_min: int, outside_min: int,
                    check_interval_min: float = 2.0) -> list[tuple]:
    """[(t, alarm_menyala)] pada tiap pemeriksaan terjadwal (seperti scheduler), dari fix pertama sampai terakhir."""
    if not fixes:
        return []
    times = [f[0] for f in fixes]
    out = []
    t = times[0]
    step = check_interval_min * 60.0
    while t <= times[-1] + 1e-9:
        hi = bisect_right(times, t)
        last = fixes[hi - 1]
        d = dist_point_to_trail_m((last[1], last[2]), trail)
        w = choose_window_minutes(d, perimeter_m, inside_min, outside_min)
        out.append((t, stagnant_at(fixes, t, w, radius_m)))
        t += step
    return out


def episodes(states: list[tuple]) -> list[tuple]:
    """Gabungkan status berurutan jadi episode alarm [(mulai, selesai)]; selesai = waktu status menyala terakhir."""
    eps, start, last_on = [], None, None
    for t, on in states:
        if on:
            if start is None:
                start = t
            last_on = t
        elif start is not None:
            eps.append((start, last_on))
            start = None
    if start is not None:
        eps.append((start, last_on))
    return eps


def score(eps: list[tuple], truth: list[tuple] | None = None, grace_s: float = 0.0) -> dict:
    """truth = [(mulai, selesai)] saat alarm jenis ini seharusnya menyala. Tanpa truth: semua episode = alarm palsu."""
    truth = truth or []
    false_alarms = 0
    for a, b in eps:
        if not any(a <= te + grace_s and b >= ts - grace_s for ts, te in truth):
            false_alarms += 1
    delays, missed = [], 0
    for ts, te in truth:
        hit = [a for a, b in eps if a <= te and b >= ts]
        if hit:
            delays.append(max(min(hit) - ts, 0.0))      # alarm yang sudah menyala sebelum mulai = tunda 0
        else:
            missed += 1
    return {"episodes": len(eps), "false_alarms": false_alarms, "detected": len(delays), "missed": missed,
            "delay_s": sorted(delays), "alarm_s": round(sum(b - a for a, b in eps), 1)}
