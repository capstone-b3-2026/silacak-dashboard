"""Tes logika murni untuk konfigurasi perangkat (stdlib unittest, tanpa DB/FastAPI):
    cd backend && python -m unittest discover -s tests -v

Fokus: rename field `sf` -> `air_data_rate`. E220 (chip LLCC68) tidak mengekspos SF,
bandwidth, dan coding rate terpisah; hanya satu setelan air data rate gabungan. Dashboard
memvalidasi himpunan 6 nilai kbps, bukan rentang SF. Nilai ini masih katalog (downlink CFG
belum dimengerti firmware), tetapi validasi dan format CFG harus konsisten memakai nama baru.
"""
import unittest

from app.api.v1 import devices
from app.api.v1.devices import DeviceIn, _check
from app.services import base_protocol as bp


class AirDataRateValidasi(unittest.TestCase):
    def test_nilai_valid_lolos(self):
        # Setiap nilai di himpunan resmi harus diterima tanpa HTTPException.
        for r in devices.AIR_DATA_RATES:
            with self.subTest(air_data_rate=r):
                _check(DeviceIn(node_id=1, name="Tracker", role="tracker",
                                config={"air_data_rate": r}))

    def test_nilai_di_luar_himpunan_ditolak_422(self):
        # 9 kbps bukan setelan E220 yang sah (9,6 yang benar). Harus 422, bukan diterima diam-diam.
        with self.assertRaises(devices.HTTPException) as cm:
            _check(DeviceIn(node_id=1, name="Tracker", role="tracker",
                            config={"air_data_rate": 9}))
        self.assertEqual(cm.exception.status_code, 422)

    def test_field_absen_tidak_gagal(self):
        # Tanpa air_data_rate, DEFAULT_CONFIG yang mengisinya; _check tidak boleh hard-fail.
        _check(DeviceIn(node_id=1, name="Tracker", role="tracker", config={}))

    def test_default_config_memakai_air_data_rate(self):
        # Default firmware = 2,4 kbps (AIR_DATA_RATE_010_24); tidak ada lagi field sf basi.
        self.assertEqual(devices.DEFAULT_CONFIG.get("air_data_rate"), 2.4)
        self.assertNotIn("sf", devices.DEFAULT_CONFIG)


class BuildCfgLine(unittest.TestCase):
    def test_cfg_memakai_air_data_rate(self):
        # build_cfg_line() harus memancarkan nilai air_data_rate (bukan membaca field sf lama).
        payload = {
            "node_id": 7, "name": "Tracker Andi", "role": "tracker", "version": 3,
            "config": {"report_interval_s": 30, "tx_power_dbm": 17, "air_data_rate": 2.4},
        }
        line = bp.build_cfg_line(payload)
        self.assertEqual(line, "CFG,7,Tracker Andi,tracker,30,17,2.4,3\n")


if __name__ == "__main__":
    unittest.main()
