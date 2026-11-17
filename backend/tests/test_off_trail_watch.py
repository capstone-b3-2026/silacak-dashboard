"""Tes aturan peringatan "di luar jalur" (off_trail_watch.py) dengan pool/koneksi/repo PALSU (tanpa Postgres).
Yang TIDAK teruji di sini: SQL sungguhan dan NOTIFY end-to-end (diuji terpisah di Postgres)."""
import asyncio
import sys
import types
import unittest

try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = types.SimpleNamespace(Pool=object, Connection=object, create_pool=None, connect=None)

from app.core import database  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import off_trail_watch as ow  # noqa: E402

# Trail acuan = segmen vertikal (bujur 110.40). Titik di dalam koridor punya bujur ~110.40;
# titik di luar digeser ~0.001 derajat bujur (~110 m, jauh di luar perimeter 50 m default).
TRAIL = [[-7.60, 110.40], [-7.59, 110.40]]
IN = {"lat": -7.595, "lon": 110.40}
OUT = {"lat": -7.595, "lon": 110.401}


class FakeConn:
    def __init__(self, st):
        self.st = st

    async def fetchval(self, sql, *args):
        if "FROM hikers" in sql:
            return 7
        return None


class FakePool:
    def __init__(self, st):
        self.st = st

    def acquire(self):
        st = self.st

        class Ctx:
            async def __aenter__(self_inner):
                return FakeConn(st)

            async def __aexit__(self_inner, *a):
                return False

        return Ctx()


def pos(code="H01", session_id=1):
    return {"hiker_code": code, "session_id": session_id, "lat": -7.595, "lon": 110.401}


class OffTrailWatch(unittest.TestCase):
    def setUp(self):
        self.st = {
            "trail": TRAIL, "fixes": [OUT, OUT, OUT], "active": False,
            "created": 0, "resolved": 0, "broadcasts": [],
        }
        self._saved = (
            database.pool,
            ow.alert_repo.get_active_alert, ow.alert_repo.create_alert, ow.alert_repo.resolve_off_trail,
            ow.position_repo.get_active_site_trail, ow.position_repo.get_recent_fixes_for_session,
            ow.notifier.broadcast,
        )
        database.pool = FakePool(self.st)
        self._orig_cfg = (settings.stagnant_perimeter_m, settings.offtrail_debounce_packets)
        st = self.st

        async def get_active(conn, session_id, alert_type):
            return {"id": 9} if st["active"] else None

        async def create(conn, hiker_id, session_id, alert_type, meta=None):
            st["created"] += 1
            st["active"] = True
            return {"id": st["created"], "alert_type": alert_type, "meta": meta}

        async def resolve(conn, session_id):
            if not st["active"]:
                return None
            st["active"] = False
            st["resolved"] += 1
            return {"id": 9, "session_id": session_id}

        async def get_trail(conn):
            return st["trail"]

        async def get_fixes(conn, session_id, limit):
            return st["fixes"][:limit]

        async def bcast(msg):
            import json
            st["broadcasts"].append(json.loads(msg))

        (ow.alert_repo.get_active_alert, ow.alert_repo.create_alert, ow.alert_repo.resolve_off_trail,
         ow.position_repo.get_active_site_trail, ow.position_repo.get_recent_fixes_for_session,
         ow.notifier.broadcast) = (get_active, create, resolve, get_trail, get_fixes, bcast)

    def tearDown(self):
        settings.stagnant_perimeter_m = self._orig_cfg[0]
        settings.offtrail_debounce_packets = self._orig_cfg[1]
        (database.pool,
         ow.alert_repo.get_active_alert, ow.alert_repo.create_alert, ow.alert_repo.resolve_off_trail,
         ow.position_repo.get_active_site_trail, ow.position_repo.get_recent_fixes_for_session,
         ow.notifier.broadcast) = self._saved

    def run_(self, *items):
        async def go():
            for d in items:
                await ow.handle_position(d)
        asyncio.run(go())

    def types_broadcast(self):
        return [m["type"] for m in self.st["broadcasts"]]

    def test_tiga_fix_di_luar_membuat_satu_alarm_dan_disiarkan(self):
        self.run_(pos())
        self.assertEqual(self.st["created"], 1)
        self.assertEqual(self.types_broadcast(), ["alert"])

    # ── ambang dibaca dari settings TIAP paket (bukan konstanta): perubahan dari halaman pengaturan langsung berlaku ──
    def test_debounce_dari_settings_dinaikkan_butuh_lebih_banyak_fix(self):
        settings.offtrail_debounce_packets = 5
        self.st["fixes"] = [OUT, OUT, OUT]  # baru 3 fix di luar, butuh 5
        self.run_(pos())
        self.assertEqual(self.st["created"], 0)
        self.st["fixes"] = [OUT] * 5
        self.run_(pos())
        self.assertEqual(self.st["created"], 1)

    def test_debounce_1_langsung_alarm_dari_satu_fix(self):
        settings.offtrail_debounce_packets = 1
        self.st["fixes"] = [OUT]
        self.run_(pos())
        self.assertEqual(self.st["created"], 1)

    def test_lebar_koridor_dari_settings_dipakai(self):
        # OUT ~110 m dari jalur: di luar koridor 50 m, tetapi di dalam koridor 200 m
        settings.stagnant_perimeter_m = 200.0
        self.run_(pos())
        self.assertEqual(self.st["created"], 0)
        settings.stagnant_perimeter_m = 50.0
        self.run_(pos())
        self.assertEqual(self.st["created"], 1)
        self.assertEqual(self.st["broadcasts"][0]["data"]["meta"]["perimeter_m"], 50.0)

    def test_sudah_ada_alarm_aktif_tidak_dobel(self):
        self.st["active"] = True
        self.run_(pos())
        self.assertEqual(self.st["created"], 0)
        self.assertEqual(self.st["broadcasts"], [])

    def test_kembali_masuk_resolve_dan_siaran_resolved(self):
        self.st["active"] = True
        self.st["fixes"] = [IN, OUT, OUT]  # terbaru kembali di dalam
        self.run_(pos())
        self.assertEqual(self.st["resolved"], 1)
        self.assertEqual(self.types_broadcast(), ["alert_resolved"])

    def test_kembali_masuk_tanpa_alarm_aktif_tidak_siaran(self):
        self.st["active"] = False
        self.st["fixes"] = [IN, IN, IN]
        self.run_(pos())
        self.assertEqual(self.st["resolved"], 0)
        self.assertEqual(self.st["broadcasts"], [])

    def test_trail_kurang_dari_dua_titik_tidak_ada_aksi(self):
        self.st["trail"] = []
        self.run_(pos())
        self.assertEqual((self.st["created"], self.st["resolved"]), (0, 0))

    def test_tanpa_pool_atau_sesi_tidak_error(self):
        database.pool = None
        self.run_(pos())
        database.pool = FakePool(self.st)
        self.run_(pos(session_id=None))
        self.assertEqual(self.st["created"], 0)


if __name__ == "__main__":
    unittest.main()
