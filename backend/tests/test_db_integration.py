"""Uji integrasi ke PostgreSQL ASLI (skema, paket ganda, NOTIFY, retensi). DILEWATI otomatis bila tidak ada database uji.

Jalankan dengan database KOSONG khusus uji, namanya HARUS berakhiran _test (tabel di dalamnya DIKOSONGKAN tiap tes):

    createdb silacak_test
    SILACAK_TEST_DB=postgresql://user:pass@127.0.0.1:5432/silacak_test python -m unittest tests.test_db_integration
"""
import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DSN = os.environ.get("SILACAK_TEST_DB", "")
OK = bool(DSN) and DSN.split("?")[0].rstrip("/").endswith("_test")


def line(seq, ago_s=3, base_ms=None):
    utc = (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"CSV_DATA,{seq},1,H01,LANGSUNG,0,{seq * 5000},{base_ms or 10000 + seq * 5000},31,{utc},-7.5912,110.4001,1450.2,1.2,9,0.95,-97,0,0"


@unittest.skipUnless(OK, "set SILACAK_TEST_DB ke DSN database uji yang namanya berakhiran _test")
class DbIntegration(unittest.TestCase):
    def run_db(self, coro_fn):
        async def main():
            import asyncpg
            from app.core import database, schema
            pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
            database.pool = pool
            try:
                async with pool.acquire() as c:
                    await schema.ensure_schema(c)
                    await c.execute("TRUNCATE positions, alerts, hiking_sessions, hikers, relay_status, link_hops, node_boots CASCADE")
                return await coro_fn(pool)
            finally:
                await pool.close()
        return asyncio.run(main())

    def test_skema_idempoten_dan_indeks_paket_unik_ada(self):
        async def go(pool):
            from app.core import schema
            async with pool.acquire() as c:
                await schema.ensure_schema(c)
                await schema.ensure_schema(c)
                self.assertTrue(await schema.packet_index_exists(c))
                await c.execute("DROP INDEX uq_positions_packet")
                self.assertFalse(await schema.packet_index_exists(c))          # yang dibaca dashboard untuk peringatan
                await schema.ensure_schema(c)
                self.assertTrue(await schema.packet_index_exists(c))
        self.run_db(go)

    def test_paket_ganda_tidak_disimpan_dan_tidak_memicu_notify(self):
        async def go(pool):
            from app.services.serial_ingest import SerialIngest
            notes = []
            lc = await pool.acquire()
            await lc.add_listener("position_updates", lambda c, pid, ch, p: notes.append(json.loads(p)))
            ing = SerialIngest()
            t = datetime.now(timezone.utc)
            for i in range(1, 6):
                await ing._handle_line(line(i), 100.0 + i, t, 0)
            await ing._handle_line(line(3), 110.0, t, 0)   # paket nomor 3 dikirim ulang
            await asyncio.sleep(0.3)
            async with pool.acquire() as c:
                self.assertEqual(await c.fetchval("SELECT count(*) FROM positions"), 5)
                self.assertEqual(await c.fetchval("SELECT count(*) FROM positions WHERE serial_read_at IS NOT NULL"), 5)
            st = ing.status()
            self.assertEqual((st["packets_received"], st["packets_duplicate"]), (5, 1))
            self.assertEqual(len(notes), 5)
            self.assertIn("serial_read_at", notes[0])
            await lc.close()
        self.run_db(go)

    def test_retensi_hanya_menghapus_sesi_selesai_yang_lewat_batas(self):
        async def go(pool):
            from app.services import retention
            async with pool.acquire() as c:
                hid = await c.fetchval("INSERT INTO hikers (hiker_code) VALUES ('H01') RETURNING id")
                now = datetime.now(timezone.utc)

                async def sess(status, out_days):
                    return await c.fetchval(
                        "INSERT INTO hiking_sessions (hiker_id, checked_in_at, checked_out_at, status) VALUES ($1,$2,$3,$4) RETURNING id",
                        hid, now - timedelta(days=out_days + 1), None if out_days is None else now - timedelta(days=out_days), status)

                old = await sess("completed", 100)
                new = await sess("completed", 5)
                emerg = await sess("emergency", 200)
                for idx, (sid, tag) in enumerate(((old, "o"), (new, "n"), (emerg, "e"))):
                    for k in range(3):
                        await c.execute("INSERT INTO positions (hiker_id, session_id, location, sequence, recorded_at) VALUES ($1,$2,point(110.4,-7.6),$3,$4)",
                                        hid, sid, k, now - timedelta(days=100 if tag == "o" else 5, minutes=k + 10 * idx))  # waktu beda tiap sesi (kunci paket unik)
                    await c.execute("INSERT INTO alerts (hiker_id, session_id, alert_type, status, triggered_at) VALUES ($1,$2,'SOS','resolved',$3)", hid, sid, now)
                await c.execute("INSERT INTO node_boots (node_id, boot_id, received_at) VALUES (1,1,$1), (1,2,$2)", now - timedelta(days=100), now)

                pv = await retention.preview(c, 30)
                self.assertEqual(pv, {"sesi": 1, "posisi": 3, "alarm": 1, "telemetri": 1})
                self.assertEqual(await retention.purge_expired(c, 0), {"sesi": 0, "posisi": 0, "alarm": 0, "telemetri": 0})
                self.assertEqual(await c.fetchval("SELECT count(*) FROM positions"), 9)   # days=0: tidak ada yang berubah

                res = await retention.purge_expired(c, 30)
                self.assertEqual(res, {"sesi": 1, "posisi": 3, "alarm": 1, "telemetri": 1})
                left = {r["id"] for r in await c.fetch("SELECT id FROM hiking_sessions")}
                self.assertEqual(left, {new, emerg})                                      # emergency tidak pernah dihapus
                self.assertEqual(await c.fetchval("SELECT count(*) FROM positions"), 6)
                self.assertEqual(await c.fetchval("SELECT count(*) FROM hikers"), 1)       # daftar pendaki tidak disentuh
                again = await retention.purge_expired(c, 30)                               # idempoten
                self.assertEqual(again, {"sesi": 0, "posisi": 0, "alarm": 0, "telemetri": 0})
        self.run_db(go)

    def test_replay_stagnan_sama_dengan_query_sql_asli(self):
        """alarm_replay.stagnant_at meniru find_stagnant_sessions; harus memberi jawaban SAMA di berbagai pola."""
        import math
        import random

        from app.repositories import position_repo
        from app.services import alarm_replay as ar

        async def go(pool):
            rng = random.Random(11)
            lat0, lon0 = -7.6, 110.4
            m_lat, m_lon = 1 / 110540.0, 1 / (111320.0 * math.cos(math.radians(lat0)))
            now = datetime.now(timezone.utc)

            def track(spec):   # spec: [(menit_lalu_awal, menit_lalu_akhir, utara_awal_m, utara_akhir_m)] tiap 30 dtk, galat 4 m
                out = []
                for a, b, n0, n1 in spec:
                    steps = int((a - b) * 2)
                    for i in range(steps):
                        ago = (a - (a - b) * i / steps) * 60.0 - 7.0          # -7 dtk: jauh dari batas jendela
                        n = n0 + (n1 - n0) * i / steps
                        out.append((now.timestamp() - ago, lat0 + (n + rng.gauss(0, 4)) * m_lat, lon0 + rng.gauss(0, 4) * m_lon))
                return sorted(out)

            scenarios = {
                "diam_90": track([(90, 0, 100, 100)]),
                "bergerak": track([(90, 0, 0, 900)]),
                "diam_20_terakhir": track([(60, 20, 0, 400), (20, 0, 400, 400)]),
                "data_baru_12_menit": track([(12, 0, 100, 100)]),
            }
            async with pool.acquire() as c:
                for code, fixes in scenarios.items():
                    hid = await c.fetchval("INSERT INTO hikers (hiker_code) VALUES ($1) RETURNING id", code)
                    for i, (t, la, lo) in enumerate(fixes):
                        await c.execute("INSERT INTO positions (hiker_id, location, sequence, recorded_at) VALUES ($1, point($2,$3), $4, to_timestamp($5))",
                                        hid, lo, la, i, t)
                checked = 0
                for window in (10, 15, 30, 60):
                    for radius in (8, 20, 60):
                        rows = await position_repo.find_stagnant_sessions(c, window, radius)
                        sql_hits = {r["hiker_id"] for r in rows}
                        for code, fixes in scenarios.items():
                            hid = await c.fetchval("SELECT id FROM hikers WHERE hiker_code=$1", code)
                            py = ar.stagnant_at(fixes, datetime.now(timezone.utc).timestamp(), window, radius)
                            self.assertEqual(py, hid in sql_hits, f"{code} window={window} radius={radius}")
                            checked += 1
                self.assertEqual(checked, 48)
        self.run_db(go)

    def test_job_retensi_tidak_menghapus_saat_dimatikan(self):
        async def go(pool):
            from app.core.config import settings
            from app.services import retention
            async with pool.acquire() as c:
                hid = await c.fetchval("INSERT INTO hikers (hiker_code) VALUES ('H01') RETURNING id")
                sid = await c.fetchval("INSERT INTO hiking_sessions (hiker_id, checked_in_at, checked_out_at, status) VALUES ($1, now()-interval '900 days', now()-interval '899 days', 'completed') RETURNING id", hid)
                await c.execute("INSERT INTO positions (hiker_id, session_id, location, sequence, recorded_at) VALUES ($1,$2,point(110.4,-7.6),1, now()-interval '899 days')", hid, sid)
            orig = settings.data_retention_days
            try:
                settings.data_retention_days = 0                # bawaan
                await retention.run_retention_job()
                async with pool.acquire() as c:
                    self.assertEqual(await c.fetchval("SELECT count(*) FROM positions"), 1)
                settings.data_retention_days = 30
                await retention.run_retention_job()
                async with pool.acquire() as c:
                    self.assertEqual(await c.fetchval("SELECT count(*) FROM positions"), 0)
            finally:
                settings.data_retention_days = orig
        self.run_db(go)


if __name__ == "__main__":
    unittest.main()
