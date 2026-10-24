"""Tes aturan alarm SOS (sos_watch.py) dengan pool/koneksi/alert_repo PALSU (tanpa Postgres).
Yang TIDAK teruji di sini: SQL sungguhan dan NOTIFY (diuji terpisah di Postgres)."""
import asyncio
import sys
import types
import unittest

try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = types.SimpleNamespace(Pool=object, Connection=object, create_pool=None, connect=None)

from app.core import database  # noqa: E402
from app.services import sos_watch as sw  # noqa: E402


class FakeConn:
    def __init__(self, st):
        self.st = st

    async def fetchval(self, sql, *args):
        if "FROM hikers" in sql:
            return 7
        if "FROM alerts" in sql:  # cek "alarm terakhir dalam jendela pengingat"
            return 1 if self.st["recent"] else None
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


def pos(code="H01", sos=True, session_id=1):
    return {"hiker_code": code, "sos": sos, "session_id": session_id, "lat": -7.58, "lon": 110.45,
            "rssi_dbm": -97, "battery_pct": 40, "route_path": "LANGSUNG"}


class SosWatch(unittest.TestCase):
    def setUp(self):
        self.st = {"active": False, "recent": False, "created": 0, "broadcast": 0}
        self._saved = (database.pool, sw.alert_repo.get_active_alert, sw.alert_repo.create_alert, sw.notifier.broadcast)
        database.pool = FakePool(self.st)
        st = self.st

        async def get_active(conn, session_id, alert_type):
            return {"id": 1} if st["active"] else None

        async def create(conn, hiker_id, session_id, alert_type, meta=None):
            st["created"] += 1
            st["active"] = True
            return {"id": st["created"], "alert_type": alert_type}

        async def bcast(msg):
            st["broadcast"] += 1

        sw.alert_repo.get_active_alert, sw.alert_repo.create_alert, sw.notifier.broadcast = get_active, create, bcast
        sw._held.clear()

    def tearDown(self):
        database.pool, sw.alert_repo.get_active_alert, sw.alert_repo.create_alert, sw.notifier.broadcast = self._saved

    def run_(self, *items):
        async def go():
            for d in items:
                await sw.handle_position(d)
        asyncio.run(go())

    def test_sos_pertama_membuat_satu_alarm_dan_disiarkan(self):
        self.run_(pos())
        self.assertEqual((self.st["created"], self.st["broadcast"]), (1, 1))

    def test_sos_terus_menyala_tidak_membuat_alarm_ganda(self):
        self.run_(pos(), pos(), pos())
        self.assertEqual(self.st["created"], 1)

    def test_sudah_ditangani_lalu_flag_masih_menyala_tidak_membuat_alarm_baru(self):
        self.run_(pos())
        self.st["active"] = False   # operator menekan "Sudah ditangani"
        self.st["recent"] = True    # alarm terakhir masih di dalam jendela pengingat
        self.run_(pos(), pos())
        self.assertEqual(self.st["created"], 1)

    def test_tombol_dilepas_lalu_ditekan_lagi_membuat_alarm_baru(self):
        self.run_(pos())
        self.st["active"] = False
        self.st["recent"] = True
        self.run_(pos(sos=False), pos())
        self.assertEqual(self.st["created"], 2)

    def test_pengingat_bila_flag_menyala_lebih_lama_dari_jendela(self):
        self.run_(pos())
        self.st["active"] = False
        self.st["recent"] = False   # alarm terakhir sudah lewat SOS_REALERT_S
        self.run_(pos())
        self.assertEqual(self.st["created"], 2)

    def test_sudah_ada_alarm_aktif_tidak_dobel_walau_tombol_baru_ditekan(self):
        self.st["active"] = True
        self.run_(pos())
        self.assertEqual(self.st["created"], 0)

    def test_tanpa_pool_atau_sesi_tidak_error(self):
        database.pool = None
        self.run_(pos())
        database.pool = FakePool(self.st)
        self.run_(pos(session_id=None))
        self.assertEqual(self.st["created"], 0)

    def test_alat_berbeda_tidak_saling_mengunci(self):
        self.run_(pos("H01"))
        self.st["active"] = False
        self.run_(pos("H02"))
        self.assertEqual(self.st["created"], 2)


if __name__ == "__main__":
    unittest.main()
