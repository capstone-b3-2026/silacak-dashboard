"""
Muat satu berkas DEM GeoTIFF sebagai lokasi aktif tanpa lewat browser.

Memakai pipeline yang sama persis dengan unggah di halaman Setup
(`app.api.v1.sites._process`): normalisasi DEM, ubin elevasi 3D, peta topo
offline, lalu lokasi ditandai aktif. Hasilnya identik dengan unggah manual.

Backend harus sudah pernah dijalankan (supaya tabel `sites` ada):

    docker compose up -d --build
    docker compose exec backend python scripts/load_sample_site.py
    docker compose exec backend python scripts/load_sample_site.py /app/samples/bukit_klangon.tif --name "Bukit Klangon"

Bawaan: /app/samples/bukit_klangon.tif (folder samples/ dipasang read-only
oleh docker-compose.yml). Prosesnya beberapa menit, tergantung komputer.

Perhatian: setelah sebuah lokasi baru aktif, backend menghapus berkas lokasi
lama di data/sites/ (baris basis datanya tetap sebagai riwayat). Karena itu
skrip menolak jalan bila sudah ada lokasi siap, kecuali dengan --force.
"""

import argparse
import asyncio
import json
import os
import shutil
import sys

# Cari folder backend/ relatif ke lokasi file ini, jadi `app.*` selalu ketemu
# apa pun folder kerja terminalnya.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.api.v1 import sites  # noqa: E402
from app.core import database  # noqa: E402

DEFAULT_TIF = "/app/samples/bukit_klangon.tif"


async def main(tif: str, name: str, force: bool) -> int:
    if not os.path.isfile(tif):
        print(f"Berkas tidak ditemukan: {tif}")
        print("Di dalam container, samples/ ada di /app/samples/ (lihat volumes di docker-compose.yml).")
        return 1
    if not tif.lower().endswith((".tif", ".tiff")):
        print("Berkas harus GeoTIFF (.tif / .tiff).")
        return 1

    await database.connect_db()
    try:
        async with database.pool.acquire() as conn:
            try:
                ready = await conn.fetchval("SELECT count(*) FROM sites WHERE status = 'ready'")
            except Exception as e:  # noqa: BLE001
                print(f"Tabel sites belum ada ({e}). Jalankan backend sekali dulu, lalu coba lagi.")
                return 1
            if ready and not force:
                print(f"Sudah ada {ready} lokasi berstatus siap. Dibatalkan supaya berkasnya tidak terhapus.")
                print("Tambahkan --force bila memang mau menggantinya.")
                return 1

            # Sama seperti POST /sites/dem: base, jalur, dan parameter lokasi aktif sebelumnya diwariskan.
            prev = await conn.fetchrow("SELECT * FROM sites WHERE is_active ORDER BY id DESC LIMIT 1")
            site_id = await conn.fetchval(
                "INSERT INTO sites (name, base, trail, params) VALUES ($1, $2, $3, $4) RETURNING id",
                name.strip() or "Lokasi contoh",
                json.dumps(sites._j(prev["base"])) if prev and prev["base"] else None,
                json.dumps(sites._j(prev["trail"]) if prev else []),
                json.dumps(sites._j(prev["params"]) if prev else {}),
            )

        folder = os.path.join(sites.SITES_DIR, str(site_id))
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(tif, os.path.join(folder, "raw.tif"))

        print(f"Memproses {tif} sebagai lokasi #{site_id} ... (bisa beberapa menit)")
        await sites._process(site_id)

        async with database.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status, message FROM sites WHERE id = $1", site_id)
        if row["status"] != "ready":
            print(f"Gagal: {row['message']}")
            return 2
        print(f"Selesai. Lokasi #{site_id} aktif. Buka http://localhost:8080 (muat ulang halaman).")
        return 0
    finally:
        await database.disconnect_db()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Muat DEM GeoTIFF sebagai lokasi aktif (setara unggah di Setup).")
    ap.add_argument("tif", nargs="?", default=DEFAULT_TIF, help=f"path GeoTIFF (bawaan {DEFAULT_TIF})")
    ap.add_argument("--name", default="Bukit Klangon", help="nama lokasi")
    ap.add_argument("--force", action="store_true", help="tetap jalan walau sudah ada lokasi siap")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.tif, a.name, a.force)))
