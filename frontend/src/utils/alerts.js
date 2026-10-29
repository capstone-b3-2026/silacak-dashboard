// Nama alarm yang mudah dibaca operator (dipakai SosOverlay dan MonitoringPanel)
const LABELS = {
  STAGNANT: "diam di tempat",
  MANUAL_SOS: "SOS manual",
  LOW_BATTERY: "baterai kritis",
  OFF_TRAIL: "di luar jalur",
};

export function alertLabel(type) {
  const t = LABELS[type] || type?.toLowerCase() || "tidak diketahui";
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// Jendela perlindungan alarm _live (ms) dari pembersihan oleh daftar server, untuk menapis race
// antara siaran SSE dan respons query /alerts. Diekspor agar tes memakai nilai yang sama.
export const LIVE_GRACE_MS = 15000;

/**
 * Rekonsiliasi daftar alarm lokal dengan daftar alarm AKTIF dari server (fungsi MURNI, tanpa Pinia,
 * bisa diuji dengan node). Server adalah sumber kebenaran untuk alarm yang masih aktif:
 *
 * - Alarm server yang belum ada di lokal (dan belum di-acked) DITAMBAHKAN sebagai _live (dibunyikan).
 * - Alarm lokal yang TIDAK ada lagi di server DIBUANG -- berarti sudah di-RESOLVE backend (mis. OFF_TRAIL
 *   saat pendaki kembali masuk perimeter) dan siaran "alert_resolved"-nya terlewat. Ini memperbaiki badge
 *   "di luar jalur" yang nyangkut.
 * - PENGECUALIAN: alarm _live yang baru masuk via SSE < graceMs dipertahankan walau belum terlihat di
 *   server (query bisa mendahului insert). Setelah grace lewat, alarm _live pun tunduk ke server.
 *
 * @param {Array<object>} current  alarm lokal sekarang (boleh memuat _live, _liveAt)
 * @param {Array<object>} serverList  alarm AKTIF dari GET /alerts
 * @param {Set<number>} acked  id alarm yang sudah ditandai selesai di browser ini
 * @param {number} nowMs  Date.now() (parameter agar tes deterministik)
 * @param {number} graceMs  jendela perlindungan _live (default LIVE_GRACE_MS)
 * @returns {Array<object>} daftar alarm baru (urutan: tambahan server terbaru dulu, lalu sisa lokal)
 */
export function reconcileAlerts(current, serverList, acked, nowMs, graceMs = LIVE_GRACE_MS) {
  const cur = Array.isArray(current) ? current : [];
  const srv = Array.isArray(serverList) ? serverList : [];
  const ack = acked || new Set();

  const have = new Set(cur.map((a) => a.id));
  const serverIds = new Set(srv.map((a) => a.id));

  const kept = cur.filter(
    (a) => serverIds.has(a.id) || (a._live && nowMs - (a._liveAt || 0) < graceMs)
  );
  const missing = srv
    .filter((a) => !have.has(a.id) && !ack.has(a.id))
    .map((a) => ({ ...a, _live: true, _liveAt: nowMs }));

  return [...missing, ...kept];
}
