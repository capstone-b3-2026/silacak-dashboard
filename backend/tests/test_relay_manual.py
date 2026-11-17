"""Relay buatan operator: jumlah bebas (0..N), tanpa saran perencana dulu; max_relays boleh 0."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.services.terrain_planner import evaluate_relay_chain, suggest_relay_chain  # noqa: E402


class Flat:
    """Medan datar 100 m di mana pun (cukup untuk menguji logika jumlah/urutan relay, bukan kalibrasi RF)."""
    def elevation_at(self, lat, lon):
        return 100.0

    def elevation_many(self, lats, lons):
        return np.full(np.shape(lats), 100.0, dtype=float)


BASE = (-7.600, 110.400)
DEG_PER_KM = 1 / 111.0
# jalur lurus ke utara sepanjang ~5 km, titik tiap 0,5 km (lebih panjang dari hop maks 2 km)
TRAIL = [(BASE[0] + k * 0.5 * DEG_PER_KM, BASE[1]) for k in range(1, 11)]
KW = dict(max_hop_km=2.0, antenna_h_m=2.0, freq_mhz=922.0)


def at_km(km):
    return (BASE[0] + km * DEG_PER_KM, BASE[1])


class RelayManual(unittest.TestCase):
    def test_tanpa_relay_tidak_error_dan_hanya_base_yang_menjangkau(self):
        evals, covered = evaluate_relay_chain(Flat(), BASE, [], TRAIL, **KW)
        self.assertEqual(evals, [])
        self.assertLess(covered, len(TRAIL) - 1, "5 km > hop maks 2 km: base saja tidak cukup")

    def test_trail_dekat_base_tercover_tanpa_relay(self):
        near = TRAIL[:2]  # <= 1 km dari base
        _, covered = evaluate_relay_chain(Flat(), BASE, [], near, **KW)
        self.assertEqual(covered, len(near) - 1)

    def test_menambah_relay_memperluas_cakupan_jumlah_relay_bebas(self):
        _, c0 = evaluate_relay_chain(Flat(), BASE, [], TRAIL, **KW)
        e1, c1 = evaluate_relay_chain(Flat(), BASE, [at_km(1.5)], TRAIL, **KW)
        e2, c2 = evaluate_relay_chain(Flat(), BASE, [at_km(1.5), at_km(3.0)], TRAIL, **KW)
        e3, c3 = evaluate_relay_chain(Flat(), BASE, [at_km(1.5), at_km(3.0), at_km(4.5)], TRAIL, **KW)
        self.assertEqual((len(e1), len(e2), len(e3)), (1, 2, 3))
        self.assertTrue(all(e.link_ok for e in e3))
        self.assertTrue(c0 < c1 < c2 <= c3)
        self.assertEqual(c3, len(TRAIL) - 1, "tiga relay manual menutup seluruh jalur 5 km")

    def test_menghapus_relay_menurunkan_cakupan(self):
        _, full = evaluate_relay_chain(Flat(), BASE, [at_km(1.5), at_km(3.0), at_km(4.5)], TRAIL, **KW)
        _, less = evaluate_relay_chain(Flat(), BASE, [at_km(1.5), at_km(3.0)], TRAIL, **KW)
        self.assertLess(less, full)

    def test_relay_yang_terlalu_jauh_dari_base_dilaporkan_putus(self):
        evals, _ = evaluate_relay_chain(Flat(), BASE, [at_km(4.5)], TRAIL, **KW)
        self.assertFalse(evals[0].link_ok)

    def test_planner_otomatis_dengan_batas_nol_hanya_menghitung_base(self):
        r = suggest_relay_chain(Flat(), BASE, TRAIL, max_relays=0, candidate_search_radius_km=0.3,
                                candidate_grid_step_km=0.06, **KW)
        self.assertEqual(r.relays, [])
        self.assertFalse(r.complete)
        self.assertEqual(r.stall_reason, "max_relays")

    def test_planner_otomatis_tanpa_relay_bila_base_cukup(self):
        r = suggest_relay_chain(Flat(), BASE, TRAIL[:2], max_relays=10, candidate_search_radius_km=0.3,
                                candidate_grid_step_km=0.06, **KW)
        self.assertEqual(r.relays, [])
        self.assertTrue(r.complete)


class ApiLayer(unittest.TestCase):
    def setUp(self):
        from app.api.v1 import sites
        self.sites = sites

    def test_max_relays_nol_diterima_negatif_kembali_ke_bawaan(self):
        self.assertEqual(self.sites._merge_params({"max_relays": 0})["max_relays"], 0)
        self.assertEqual(self.sites._merge_params({"max_relays": 3})["max_relays"], 3)
        for bad in (-1, "", None, True, float("nan")):
            self.assertEqual(self.sites._merge_params({"max_relays": bad})["max_relays"], 10, repr(bad))

    def test_relay_move_menerima_nol_sampai_batas_dan_menolak_data_rusak(self):
        from pydantic import ValidationError
        RM = self.sites.RelayMove
        self.assertEqual(RM(relays=[]).relays, [])
        self.assertEqual(len(RM(relays=[[-7.6, 110.4]] * 50).relays), 50)
        for bad in ([[1.0]], [[1.0, 2.0, 3.0]], [[float("nan"), 1.0]], [[95.0, 1.0]], [[1.0, 200.0]], [[-7.6, 110.4]] * 51):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                RM(relays=bad)


if __name__ == "__main__":
    unittest.main()
