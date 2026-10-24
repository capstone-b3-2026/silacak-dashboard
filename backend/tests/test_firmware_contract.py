"""Tes KONTRAK firmware -> backend. Baris GOLDEN adalah keluaran emitCsvData() / handleTimingPacket() base_real.cpp
yang dikompilasi di host (g++) dengan DataPacket uji. Field ke-19 (baterai %) dan ke-20 (SOS) adalah kontrak untuk
firmware BARU: kalau firmware memakai urutan lain, ubah OPTIONAL_FIELDNAMES di base_protocol.py bersamaan."""
import unittest
from datetime import datetime, timezone

from app.services import base_protocol as bp

NOW = datetime(2026, 10, 22, 5, 0, 0, tzinfo=timezone.utc)
FIX = "CSV_DATA,10,1,Pendaki A,LANGSUNG,0,50000,50123,31,2026-10-20T03:09:36Z,-7.5848750,110.4500750,2900.50,1.23,9,0.95,-97,0,0"
NOFIX = "CSV_DATA,11,2,Pendaki B,LANGSUNG,0,60000,60100,0,-,0.0000000,0.0000000,0.00,0.00,0,99.99,-110,2,5"
RELAYED = "CSV_DATA,12,3,Pendaki C,R101>R102,2,0,70000,23,2026-10-20T03:10:00Z,-7.5000000,110.4000000,0.00,0.00,7,1.50,-120,0,1"
TIMING = "CSV_TIMING,10,1,Pendaki A,1840,920.0"
BAT = FIX + ",73,0"                       # firmware baru: baterai 73%, tanpa SOS
SOS = NOFIX + ",41,1"                     # SOS saat tanpa GPS fix


def rec(line):
    return bp.to_record(bp.parse_csv_data(line), NOW)


class FirmwareContract(unittest.TestCase):
    def test_18_field_terpetakan_berurutan(self):
        row = bp.parse_csv_data(FIX)
        self.assertEqual(list(row), bp.FIELDNAMES)
        self.assertEqual((row["sequence"], row["node_id"], row["relay_hops"], row["rssi_dbm"]), ("10", "1", "0", "-97"))

    def test_fix_penuh(self):
        r = rec(FIX)
        self.assertEqual((r.hiker_code, r.lat, r.lon, r.elevation, r.speed_kph), ("H01", -7.584875, 110.450075, 2900.5, 1.23))
        self.assertTrue(r.gps_valid and r.time_from_gps)

    def test_tanpa_fix_tidak_menyimpan_nol_palsu(self):
        r = rec(NOFIX)
        self.assertEqual((r.lat, r.lon, r.elevation, r.speed_kph), (None, None, None, None))
        self.assertFalse(r.gps_valid)

    def test_altitude_nol_palsu_dibuang_tapi_speed_nol_sah_dipertahankan(self):
        r = rec(RELAYED)
        self.assertIsNone(r.elevation)
        self.assertEqual(r.speed_kph, 0.0)
        self.assertEqual((r.hop_count, r.route_path), (2, "R101>R102"))

    def test_flags_kosong_data_lama_dipakai_apa_adanya(self):
        row = bp.parse_csv_data(FIX)
        row["gps_flags"] = ""
        self.assertEqual(bp.to_record(row, NOW).elevation, 2900.5)

    def test_timing(self):
        self.assertEqual(bp.parse_csv_timing(TIMING), {"sequence": 10, "node_id": 1, "rtt_ms": 1840})
        self.assertIsNone(bp.parse_csv_timing(FIX))
        self.assertIsNone(bp.parse_csv_timing("CSV_TIMING,10,1,Pendaki A"))
        self.assertIsNone(bp.parse_csv_timing("CSV_TIMING,x,1,Pendaki A,1840,920.0"))

    # ── baterai & SOS (field ke-19, ke-20) ──
    def test_firmware_lama_18_field_tanpa_baterai_dan_sos(self):
        r = rec(FIX)
        self.assertIsNone(r.battery_pct)
        self.assertFalse(r.sos)

    def test_baterai_dibaca(self):
        r = rec(BAT)
        self.assertEqual(r.battery_pct, 73.0)
        self.assertFalse(r.sos)
        self.assertEqual(r.lat, -7.584875)  # field lama tidak bergeser

    def test_sos_aktif_walau_tanpa_gps_fix(self):
        r = rec(SOS)
        self.assertTrue(r.sos)
        self.assertEqual(r.battery_pct, 41.0)
        self.assertIsNone(r.lat)

    def test_baterai_tidak_terbaca_jadi_null_bukan_255_persen(self):
        for bad in ("255", "-1", "101", "-", "", "abc"):
            self.assertIsNone(rec(FIX + f",{bad},0").battery_pct, bad)

    def test_sos_hanya_angka_1(self):
        for v, expected in (("1", True), ("0", False), ("", False), ("-", False), ("2", False), ("x", False), ("true", False)):
            self.assertEqual(rec(FIX + f",50,{v}").sos, expected, v)

    def test_baris_20_field_tidak_ditolak_dan_hanya_satu_field_baterai(self):
        self.assertIsNotNone(bp.parse_csv_data(BAT))
        self.assertIsNone(bp.parse_csv_data("CSV_DATA,1,2,3"))  # kurang dari 18 field tetap ditolak


if __name__ == "__main__":
    unittest.main()