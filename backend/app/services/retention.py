"""Kebijakan masa simpan data (retensi). BAWAAN MATI: data_retention_days = 0 berarti simpan selamanya.

Yang dihapus bila diaktifkan (N hari):
- Sesi pendakian berstatus `completed` yang check-out-nya lebih lama dari N hari, beserta titik posisinya (lokasi pendaki)
  dan alarmnya.
- Alarm lama yang sudah tidak aktif dan tidak terkait sesi.
- Titik posisi yatim (tanpa sesi) yang diterima lebih dari N hari lalu.
- Telemetri jaringan (relay_status, link_hops, node_boots) lebih lama dari N hari. Ini bukan data pribadi, hanya dibersihkan agar
  tabelnya tidak membengkak.

TIDAK disentuh: sesi `active`/`emergency` (apa pun umurnya), daftar pendaki (hikers: nama, telepon, kontak darurat), alat, dan
lokasi (DEM/jalur). Data identitas pendaki dihapus operator secara terpisah.

Penghapusan TIDAK BISA dibatalkan. Angka N yang sah menurut UU Pelindungan Data Pribadi ditentukan lembaga pengelola
(pengendali data) bersama penasihat hukumnya; aplikasi ini hanya menyediakan mekanismenya dan tidak menentukan angkanya.
"""
from __future__ import annotations

import logging

from app.core import database
from app.core.config import settings

log = logging.getLogger("silacak.retention")

# Sesi yang sudah lewat batas. `completed` saja: sesi 'emergency' bisa saja belum selesai ditangani.
_OLD_SESSIONS = """
    SELECT id FROM hiking_sessions
    WHERE status = 'completed' AND checked_out_at IS NOT NULL
      AND checked_out_at < now() - make_interval(days => $1)
"""


async def preview(conn, days: int) -> dict:
    """Berapa baris yang AKAN dihapus untuk batas `days` hari (tidak menghapus apa pun)."""
    q = {
        "sesi": f"SELECT count(*) FROM hiking_sessions WHERE id IN ({_OLD_SESSIONS})",
        "posisi": f"""SELECT count(*) FROM positions
                      WHERE session_id IN ({_OLD_SESSIONS})
                         OR (session_id IS NULL AND received_at < now() - make_interval(days => $1))""",
        "alarm": f"""SELECT count(*) FROM alerts
                     WHERE session_id IN ({_OLD_SESSIONS})
                        OR (session_id IS NULL AND status <> 'active' AND triggered_at < now() - make_interval(days => $1))""",
        "telemetri": """SELECT (SELECT count(*) FROM relay_status WHERE received_at < now() - make_interval(days => $1))
                             + (SELECT count(*) FROM link_hops WHERE received_at < now() - make_interval(days => $1))
                             + (SELECT count(*) FROM node_boots WHERE received_at < now() - make_interval(days => $1))""",
    }
    return {k: await conn.fetchval(sql, int(days)) for k, sql in q.items()}


async def purge_expired(conn, days: int) -> dict:
    """Hapus data yang melewati batas `days` hari. days <= 0 = tidak menghapus apa pun. Satu transaksi: semua atau tidak sama sekali."""
    days = int(days)
    if days <= 0:
        return {"sesi": 0, "posisi": 0, "alarm": 0, "telemetri": 0}
    out = {}
    async with conn.transaction():
        # Urutan penting: anak (posisi, alarm) dulu, baru sesi (foreign key).
        out["posisi"] = _n(await conn.execute(
            f"""DELETE FROM positions
                WHERE session_id IN ({_OLD_SESSIONS})
                   OR (session_id IS NULL AND received_at < now() - make_interval(days => $1))""", days))
        out["alarm"] = _n(await conn.execute(
            f"""DELETE FROM alerts
                WHERE session_id IN ({_OLD_SESSIONS})
                   OR (session_id IS NULL AND status <> 'active' AND triggered_at < now() - make_interval(days => $1))""", days))
        out["sesi"] = _n(await conn.execute(f"DELETE FROM hiking_sessions WHERE id IN ({_OLD_SESSIONS})", days))
        tele = 0
        for table in ("relay_status", "link_hops", "node_boots"):
            tele += _n(await conn.execute(f"DELETE FROM {table} WHERE received_at < now() - make_interval(days => $1)", days))
        out["telemetri"] = tele
    return out


def _n(status: str) -> int:
    """'DELETE 12' -> 12"""
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except ValueError:
        return 0


async def run_retention_job() -> None:
    """Dipanggil terjadwal (harian). Nilai dibaca TIAP jalan supaya perubahan dari halaman pengaturan langsung berlaku."""
    days = int(settings.data_retention_days)
    if days <= 0 or database.pool is None:
        return
    try:
        async with database.pool.acquire() as conn:
            res = await purge_expired(conn, days)
        if any(res.values()):
            log.warning("Retensi %d hari: dihapus %s", days, res)
    except Exception:  # noqa: BLE001 - kegagalan retensi tidak boleh mengganggu aplikasi
        log.exception("Retensi data gagal")
