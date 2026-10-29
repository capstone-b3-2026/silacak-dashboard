// Tes logika rekonsiliasi alarm (tanpa Pinia/browser). Jalankan: node frontend/src/utils/alerts.test.mjs
import assert from "node:assert/strict";
import { reconcileAlerts, LIVE_GRACE_MS, alertLabel } from "./alerts.js";

const NOW = 1_000_000;

// alertLabel: nama ramah operator
assert.equal(alertLabel("OFF_TRAIL"), "Di luar jalur");
assert.equal(alertLabel("MANUAL_SOS"), "SOS manual");
assert.equal(alertLabel(undefined), "Tidak diketahui");

// Alarm server BARU (belum ada lokal) ditambahkan sebagai _live
{
  const out = reconcileAlerts([], [{ id: 1, alert_type: "OFF_TRAIL" }], new Set(), NOW);
  assert.equal(out.length, 1);
  assert.equal(out[0].id, 1);
  assert.equal(out[0]._live, true);
  assert.equal(out[0]._liveAt, NOW);
}

// INTI BUG: alarm lokal yang sudah di-RESOLVE backend (tidak ada di server) DIBUANG.
// Alarm #9 sudah pernah dimuat (bukan _live) dan server sekarang kosong -> harus hilang.
{
  const current = [{ id: 9, alert_type: "OFF_TRAIL" }];
  const out = reconcileAlerts(current, [], new Set(), NOW);
  assert.deepEqual(out, [], "alarm yang sudah resolved di server harus dibuang");
}

// Alarm _live yang BARU SAJA masuk via SSE (< grace) DIPERTAHANKAN walau belum terlihat server (race)
{
  const current = [{ id: 5, alert_type: "MANUAL_SOS", _live: true, _liveAt: NOW - 1000 }];
  const out = reconcileAlerts(current, [], new Set(), NOW);
  assert.equal(out.length, 1, "alarm _live dalam grace tidak boleh dibuang");
  assert.equal(out[0].id, 5);
}

// Alarm _live yang SUDAH LEWAT grace tunduk ke server: tidak ada di server -> dibuang
{
  const current = [{ id: 5, alert_type: "OFF_TRAIL", _live: true, _liveAt: NOW - LIVE_GRACE_MS - 1 }];
  const out = reconcileAlerts(current, [], new Set(), NOW);
  assert.deepEqual(out, [], "alarm _live setelah grace harus tunduk ke server");
}

// Alarm _live yang MASIH ada di server tetap dipertahankan (apa pun umurnya)
{
  const current = [{ id: 7, alert_type: "MANUAL_SOS", _live: true, _liveAt: NOW - 999999 }];
  const out = reconcileAlerts(current, [{ id: 7, alert_type: "MANUAL_SOS" }], new Set(), NOW);
  assert.equal(out.length, 1);
  assert.equal(out[0].id, 7);
}

// acked: alarm server yang sudah ditandai selesai di browser ini TIDAK dimunculkan lagi
{
  const out = reconcileAlerts([], [{ id: 3 }], new Set([3]), NOW);
  assert.deepEqual(out, [], "alarm yang sudah di-acked tidak boleh muncul lagi");
}

// Gabungan: satu tetap (ada di server), satu dibuang (resolved), satu baru dari server
{
  const current = [
    { id: 1, alert_type: "MANUAL_SOS" }, // masih di server -> tetap
    { id: 2, alert_type: "OFF_TRAIL" }, // tidak di server -> dibuang
  ];
  const server = [{ id: 1, alert_type: "MANUAL_SOS" }, { id: 4, alert_type: "STAGNANT" }];
  const out = reconcileAlerts(current, server, new Set(), NOW);
  const ids = out.map((a) => a.id).sort();
  assert.deepEqual(ids, [1, 4]);
  // yang baru (#4) ditandai _live, yang lama (#1) tidak diubah
  assert.equal(out.find((a) => a.id === 4)._live, true);
}

// Input aneh tidak melempar
assert.deepEqual(reconcileAlerts(null, null, null, NOW), []);

console.log("alerts: semua OK");
