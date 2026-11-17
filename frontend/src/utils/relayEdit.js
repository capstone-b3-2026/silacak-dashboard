// Penyuntingan daftar relay oleh operator (murni, tanpa Vue/Pinia supaya bisa diuji di Node).
// Daftar relay = urutan R1, R2, ... di plan.relays; backend menilai ulang rantai tiap kali daftar baru disimpan.

export const MAX_RELAYS = 50; // sama dengan MAX_MANUAL_RELAYS di backend/app/api/v1/sites.py

const round6 = (v) => Math.round(v * 1e6) / 1e6;

// plan.relays -> [[lat, lon], ...] (urutan dipertahankan)
export function relayPoints(plan) {
  return (plan?.relays || []).map((r) => [r.lat, r.lon]);
}

// Tambah relay di ujung (jadi R(n+1)). Relay baru hanya bisa tersambung ke base atau relay bernomor lebih kecil.
export function withAdded(plan, lat, lon) {
  const cur = relayPoints(plan);
  if (cur.length >= MAX_RELAYS) throw new Error(`Maksimal ${MAX_RELAYS} relay.`);
  return [...cur, [round6(lat), round6(lon)]];
}

// Hapus relay bernomor n. Relay sesudahnya otomatis bergeser nomornya (R3 jadi R2, dst.).
export function withRemoved(plan, n) {
  return (plan?.relays || []).filter((r) => r.n !== n).map((r) => [r.lat, r.lon]);
}

// Pindahkan relay bernomor n.
export function withMoved(plan, n, lat, lon) {
  return (plan?.relays || []).map((r) => (r.n === n ? [round6(lat), round6(lon)] : [r.lat, r.lon]));
}

// Alat relay memakai nomor posisi (plan_slot = "R<n>"). Menghapus Rn menggeser R(n+1).. turun satu, jadi slot alat
// harus ikut digeser supaya tiap alat tetap menunjuk relay FISIK yang sama (rute paket "R5>R6" di peta memakai slot).
// Kembalian: [[id, slotBaru|null], ...] BERURUTAN (kosongkan dulu slot n, lalu geser naik) supaya tidak bentrok dengan
// batas unik "satu slot satu alat" di backend.
export function slotShiftAfterRemoval(devices, n) {
  const out = [];
  const withSlot = (devices || []).filter((d) => d.plan_slot != null);
  for (const d of withSlot) if (d.plan_slot === n) out.push([d.id, null]);
  for (const d of withSlot.filter((x) => x.plan_slot > n).sort((a, b) => a.plan_slot - b.plan_slot)) out.push([d.id, d.plan_slot - 1]);
  return out;
}
