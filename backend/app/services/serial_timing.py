"""Ukur PENUMPUKAN paket antara penerimaan radio di base dan pembacaan serial di laptop (fungsi MURNI, tanpa serial/DB).

Tiap baris CSV_DATA membawa `base_received_uptime_ms` = jam internal base (millis) saat paket radio diterima. Laptop mencatat
jam monotonic-nya saat baris itu DIBACA dari serial. Dua jam itu tidak perlu disinkronkan: yang dibandingkan adalah SELISIH
antarpaket.

    D_i     = (baca_i - baca_0) - (base_i - base_0)       # nilai konstan hilang; naik = paket tertahan sebelum terbaca
    tunda_i = D_i - min(D dalam jendela)                  # penundaan ekstra dibanding paket yang paling lancar

Paket yang tertahan lalu dilepas sekaligus (buffer USB/driver/firmware) tampil sebagai: selisih baca jauh lebih kecil daripada
selisih base ("terkumpul"). Pembedaan sumber penumpukan:

  - `host_tertinggal`: laptop sendiri lambat (pemrosesan per paket >= ~1 dtk atau ada data menunggu di buffer serial
    setelah satu baris dibaca). Perbaikan di sisi aplikasi/DB.
  - `tertahan_sebelum_dibaca`: laptop membaca cepat dan buffer kosong, tetapi paket tiba berkelompok. Penahan ada SEBELUM
    pembacaan: antrean kirim serial di firmware base, buffer/latency timer chip USB-serial, atau driver. Perlu bukti di sisi
    firmware (mis. hitung kedalaman antrean TX serial base) untuk memastikan yang mana.
  - `tidak_ada_penumpukan`: penundaan ekstra kecil.

Batas pengukuran (jangan dilebih-lebihkan): menangkap penundaan RELATIF dalam jendela, bukan latensi absolut; jam kristal
ESP32 dan laptop bergeser puluhan ppm (sekitar 0,2 dtk/jam), jadi jendela dibatasi (default 600 paket) dan baseline-nya
dihitung ulang di dalamnya. Penahan yang SELALU sama besar (mis. tiap paket tertahan 2 dtk tepat) tidak terlihat.
"""
from __future__ import annotations

import time
from collections import deque

MIN_PACKETS = 20          # di bawah ini verdict = belum_cukup_data
CATCHUP_S = 0.5           # baca lebih cepat dari terima sebesar ini (dtk) = satu kejadian "terkumpul"
EXTRA_DELAY_OK_S = 0.25   # p95 tunda ekstra di bawah ini dianggap tidak ada penumpukan
SLOW_PROC_MS = 1000.0     # pemrosesan per paket (baca -> tersimpan di DB) setinggi ini = host lambat
BACKLOG_BYTES = 150       # sisa byte di buffer serial setelah satu baris dibaca; ~1 baris CSV_DATA
BASE_RESET_BACK_MS = 1000  # base_ms mundur lebih dari ini = base reboot -> mulai referensi baru
BASE_MAX_FWD_S = 3600     # lompatan maju base_ms lebih dari 1 jam antar paket = tidak masuk akal -> mulai referensi baru


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(float(v), nd)


class TimingBuffer:
    def __init__(self, maxlen: int = 600) -> None:
        self._e: deque[dict] = deque(maxlen=maxlen)
        self._epoch = 0
        self._last_base_ms: int | None = None
        self.resets = 0

    def add(self, read_mono: float, base_ms: int | None, backlog_bytes: int | None = None, proc_ms: float | None = None) -> None:
        """Catat satu paket. base_ms None (firmware lama tanpa field itu) dilewati: tanpa jam base tak ada yang bisa dibandingkan."""
        if base_ms is None:
            return
        if self._last_base_ms is not None:
            back = self._last_base_ms - base_ms
            fwd_s = (base_ms - self._last_base_ms) / 1000.0
            if back > BASE_RESET_BACK_MS or fwd_s > BASE_MAX_FWD_S:
                self._epoch += 1  # base reboot / wrap uint32 / data tidak sinambung
                self.resets += 1
        self._last_base_ms = base_ms
        self._e.append({"mono": float(read_mono), "base_ms": int(base_ms), "epoch": self._epoch,
                        "backlog": backlog_bytes, "proc_ms": proc_ms})

    def stats(self) -> dict:
        ent = list(self._e)
        out: dict = {"n": len(ent), "base_resets": self.resets}
        if not ent:
            out.update(verdict="belum_cukup_data", explanation="Belum ada paket CSV_DATA dengan jam base.")
            return out
        cur = [e for e in ent if e["epoch"] == ent[-1]["epoch"]]  # hanya sejak base reboot terakhir
        out["n_epoch"] = len(cur)
        out["window_s"] = _r(cur[-1]["mono"] - cur[0]["mono"], 1)
        # D_i relatif terhadap paket pertama; tunda ekstra = D_i - min(D)
        d = [(e["mono"] - cur[0]["mono"]) - (e["base_ms"] - cur[0]["base_ms"]) / 1000.0 for e in cur]
        base = min(d)
        extra = [x - base for x in d]
        catch = []  # seberapa jauh baca "mengejar" terima antar dua paket berurutan
        for a, b in zip(cur, cur[1:]):
            read_gap = b["mono"] - a["mono"]
            base_gap = (b["base_ms"] - a["base_ms"]) / 1000.0
            if base_gap - read_gap > CATCHUP_S:
                catch.append(base_gap - read_gap)
        bl = [e["backlog"] for e in cur if e["backlog"] is not None]
        pm = [e["proc_ms"] for e in cur if e["proc_ms"] is not None]
        out["tunda_ekstra_s"] = {"p50": _r(_pct(extra, .5)), "p95": _r(_pct(extra, .95)), "max": _r(max(extra))}
        out["terkumpul"] = {"kejadian": len(catch), "maks_s": _r(max(catch) if catch else 0.0),
                            "persen_paket": _r(100.0 * len(catch) / max(len(cur) - 1, 1), 1)}
        out["backlog_byte"] = {"p95": _r(_pct(bl, .95), 0), "max": max(bl) if bl else None}
        out["proses_ms"] = {"p50": _r(_pct(pm, .5), 1), "p95": _r(_pct(pm, .95), 1), "max": _r(max(pm), 1) if pm else None}

        if len(cur) < MIN_PACKETS:
            out.update(verdict="belum_cukup_data", explanation=f"Baru {len(cur)} paket sejak base terakhir menyala; butuh minimal {MIN_PACKETS}.")
            return out
        p95 = out["tunda_ekstra_s"]["p95"] or 0.0
        slow = (out["proses_ms"]["p95"] or 0.0) >= SLOW_PROC_MS or (out["backlog_byte"]["p95"] or 0) >= BACKLOG_BYTES
        if p95 < EXTRA_DELAY_OK_S and not catch:
            out.update(verdict="tidak_ada_penumpukan", explanation="Paket dibaca laptop selaras dengan saat diterima base.")
        elif slow:
            out.update(verdict="host_tertinggal",
                       explanation="Laptop terlambat membaca: pemrosesan per paket lama atau ada data menunggu di buffer serial. "
                                   "Periksa kecepatan database dan beban laptop.")
        else:
            out.update(verdict="tertahan_sebelum_dibaca",
                       explanation="Laptop membaca cepat dan buffer kosong, tetapi paket tiba berkelompok. Penahan ada sebelum "
                                   "pembacaan (antrean serial di base, buffer/latency timer USB-serial, atau driver). Lanjutkan "
                                   "dengan mengukur kedalaman antrean TX serial di firmware base.")
        return out


def now_mono() -> float:
    return time.monotonic()
