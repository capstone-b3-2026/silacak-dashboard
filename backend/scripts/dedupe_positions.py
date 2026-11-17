"""Bersihkan paket ganda lama di tabel positions supaya indeks uq_positions_packet bisa dibuat.

Paket ganda = baris dengan (hiker_id, sequence, recorded_at, sos) sama dan sequence tidak NULL. Yang DIPERTAHANKAN: baris
dengan received_at paling awal (paket pertama yang sampai). Bawaan = DRY RUN (hanya menghitung); hapus sungguhan dengan --apply.
CADANGKAN database dulu bila datanya penting. Pakai DATABASE_URL dari .env/lingkungan.

    python scripts/dedupe_positions.py            # lihat dulu berapa baris ganda
    python scripts/dedupe_positions.py --apply    # hapus baris ganda
"""
import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.config import settings  # noqa: E402

DUP_CTE = """
WITH ranked AS (
    SELECT ctid AS row_id,
           row_number() OVER (PARTITION BY hiker_id, sequence, recorded_at, sos ORDER BY received_at, ctid) AS rn
    FROM positions
    WHERE sequence IS NOT NULL
)
"""


async def main(apply: bool) -> int:
    conn = await asyncpg.connect(settings.database_url)
    try:
        n = await conn.fetchval(DUP_CTE + "SELECT count(*) FROM ranked WHERE rn > 1")
        print(f"Baris ganda ditemukan: {n}")
        if not n or not apply:
            if n:
                print("Dry run: tidak ada yang dihapus. Tambahkan --apply untuk menghapus.")
            return 0
        async with conn.transaction():
            status = await conn.execute(
                DUP_CTE + "DELETE FROM positions WHERE ctid IN (SELECT row_id FROM ranked WHERE rn > 1)")
        print(f"Selesai ({status}). Mulai ulang backend agar indeks uq_positions_packet dibuat.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="hapus baris ganda (bawaan: dry run)")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
