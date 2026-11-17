"""Tes SerialIngest end-to-end dengan pool/koneksi PALSU (tanpa Postgres, tanpa pyserial/FastAPI):
memastikan alur baris serial -> argumen INSERT konsisten dengan SQL, log mentah, cache, filter relay, status.
Yang TIDAK teruji: SQL sungguhan di Postgres."""
import asyncio
import json
import os
import re
import sys
import tempfile
import types
import unittest

# stub minimal HANYA kalau paket aslinya tidak terpasang (di mesin dev/CI paket asli dipakai)
try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = types.SimpleNamespace(Pool=object, Connection=object, create_pool=None, connect=None)
try:
    import pydantic_settings  # noqa: F401
except ImportError:
    class _BS:
        def __init__(self):
            for k, v in list(type(self).__dict__.items()):
                pass
    def _mk():
        ns = types.ModuleType("pydantic_settings")
        class BaseSettings:
            def __init__(self):
                for k in getattr(type(self), "__annotations__", {}):
                    setattr(self, k, getattr(type(self), k, None))
        ns.BaseSettings = BaseSettings
        ns.SettingsConfigDict = lambda **kw: kw
        return ns
    sys.modules["pydantic_settings"] = _mk()

from app.core import database  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import serial_ingest as si  # noqa: E402

FIX = "CSV_DATA,123,1,H01,LANGSUNG,0,45000,45010,31,2026-07-01T03:04:05Z,-7.5912345,110.4001234,1450.20,1.20,9,0.95,-97,2,5"
NOFIX = "CSV_DATA,124,1,H01,LANGSUNG,0,50000,50020,0,-,0.0000000,0.0000000,0.00,0.00,0,0.00,-101,0,5"
RELAY = "CSV_DATA,5,5,R05,LANGSUNG,0,1,2,31,2026-07-01T03:04:05Z,-7.59,110.40,1400.00,0.00,8,1.00,-90,0,0"


class FakeConn:
    def __init__(self, log, roles):
        self.log, self.roles = log, roles

    async def fetchval(self, sql, *args):
        self.log.append(("fetchval", sql, args))
        if "FROM devices" in sql:
            return self.roles.get(args[0])
        if "INSERT INTO hikers" in sql:
            return 77
        return None

    async def execute(self, sql, *args):
        self.log.append(("execute", sql, args))


class FakePool:
    def __init__(self, roles=None):
        self.log, self.roles = [], roles or {}

    def acquire(self):
        pool = self

        class Ctx:
            async def __aenter__(self_):
                return FakeConn(pool.log, pool.roles)

            async def __aexit__(self_, *a):
                return False
        return Ctx()


class Ingest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings.data_dir = self.tmp.name
        settings.raw_log = True
        self.pool = FakePool({5: "relay"})
        database.pool = self.pool
        self.ing = si.SerialIngest()

    def tearDown(self):
        database.pool = None
        self.tmp.cleanup()

    def run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def inserts(self):
        return [e for e in self.pool.log if e[0] == "execute" and "INSERT INTO positions" in e[1]]

    def test_jumlah_placeholder_sama_dengan_argumen(self):
        self.run_async(self.ing._handle_line(FIX))
        (_, sql, args), = self.inserts()
        self.assertEqual(max(int(n) for n in re.findall(r"\$(\d+)", sql)), len(args))

    def test_urutan_argumen_sesuai_kolom(self):
        self.run_async(self.ing._handle_line(FIX))
        (_, sql, a), = self.inserts()
        # $1 hiker_id, $2 lon, $3 lat, $4 elevation, ... (lihat INSERT di _store)
        self.assertEqual(a[0], 77)
        self.assertAlmostEqual(a[1], 110.4001234)   # lon
        self.assertAlmostEqual(a[2], -7.5912345)    # lat
        self.assertEqual(a[3], 1450.20)             # elevation
        self.assertEqual(a[5], "LANGSUNG")          # route_path
        self.assertEqual(a[6], 123)                 # sequence
        self.assertEqual(a[7], -97)                 # rssi
        self.assertEqual(a[12].year, 2026)          # recorded_at dari jam GPS
        self.assertIs(a[13], True)                  # gps_valid
        self.assertEqual(a[14], "31")               # gps_flags mentah
        self.assertIs(a[15], True)                  # time_from_gps
        self.assertIn("point($2::float8, $3::float8)", sql)
        self.assertEqual(self.ing.status()["packets_received"], 1)

    def test_tanpa_fix_masuk_dengan_lokasi_null(self):
        self.run_async(self.ing._handle_line(NOFIX))
        (_, _, a), = self.inserts()
        self.assertIsNone(a[1])
        self.assertIsNone(a[2])
        self.assertIs(a[13], False)   # gps_valid
        self.assertIs(a[15], False)   # waktu bukan dari GPS (gps_utc '-')

    def test_relay_tidak_jadi_pendaki(self):
        self.run_async(self.ing._handle_line(RELAY))
        self.assertEqual(self.inserts(), [])
        self.assertFalse(any("INSERT INTO hikers" in e[1] for e in self.pool.log))

    def test_cache_hindari_query_berulang(self):
        for _ in range(5):
            self.run_async(self.ing._handle_line(FIX))
        self.assertEqual(len(self.inserts()), 5)
        self.assertEqual(sum("FROM devices" in e[1] for e in self.pool.log), 1)  # peran node dicari sekali

    def test_serial_read_at_dicatat_dan_paket_ganda_tidak_dihitung_diterima(self):
        from datetime import datetime, timezone
        t = datetime(2026, 11, 16, 3, 0, 0, tzinfo=timezone.utc)
        self.run_async(self.ing._handle_line(FIX, 123.0, t, 0))
        (_, sql, a), = self.inserts()
        self.assertEqual(a[19], t)                       # $20 serial_read_at = saat baris DIBACA, bukan saat insert
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertEqual((self.ing.status()["packets_received"], self.ing.status()["packets_duplicate"]), (1, 0))
        # DB menjawab "INSERT 0 0" (ditolak indeks unik) -> dihitung ganda, BUKAN diterima
        orig = FakeConn.execute

        async def dup(self_, sql, *args):
            await orig(self_, sql, *args)
            return "INSERT 0 0"
        FakeConn.execute = dup
        try:
            self.run_async(self.ing._handle_line(FIX))
        finally:
            FakeConn.execute = orig
        self.assertEqual((self.ing.status()["packets_received"], self.ing.status()["packets_duplicate"]), (1, 1))

    def test_jam_base_masuk_pengukur_penumpukan(self):
        self.run_async(self.ing._handle_line(FIX, 50.0, None, 0))
        self.assertEqual(self.ing.timing_stats()["n"], 1)            # FIX membawa base_received_uptime_ms=45010
        self.run_async(self.ing._handle_line(NOFIX, 55.0, None, None))
        self.assertEqual(self.ing.timing_stats()["n"], 2)

    def test_baris_rusak_dihitung_ditolak(self):
        self.run_async(self.ing._handle_line("CSV_DATA,1,2"))
        self.assertEqual(self.ing.status()["packets_rejected"], 1)

    def test_log_mentah_append_only(self):
        self.ing._write_raw(FIX)
        self.ing._write_raw(NOFIX)
        folder = os.path.join(self.tmp.name, "raw")
        (name,) = os.listdir(folder)
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("," + FIX))  # "<waktu terima>,<baris asli>" -> bisa diputar ulang
        self.ing._raw_fh.close()

    def test_pilihan_port_tersimpan_dan_dimuat_lagi(self):
        self.ing.set_port("COM9")
        with open(os.path.join(self.tmp.name, "base_link.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["port"], "COM9")
        other = si.SerialIngest()
        other._load_pref()
        self.assertEqual(other.status()["requested"], "COM9")

    def test_status_awal_off(self):
        settings.serial_port = "off"
        self.assertEqual(si.SerialIngest().status()["state"], "off")


if __name__ == "__main__":
    unittest.main()
