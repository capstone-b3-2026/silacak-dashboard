import { defineStore } from "pinia";
import { acknowledgeAlert, fetchAlerts } from "../services/api";

// Alarm yang sudah ditandai "Sudah ditangani" di browser ini. Mencegah respons /alerts yang masih dalam
// perjalanan (diminta sebelum tombol ditekan) memunculkan lagi alarm tersebut + bunyi ulang.
const acked = new Set();

// Waktu dari server -> epoch ms. SSE mengirim "2026-10-27 10:00:00.123456+00:00" (spasi, 6 digit pecahan),
// REST mengirim ISO. Dinormalkan dulu supaya terbaca di semua browser; null bila tidak terbaca.
function toMs(v) {
  if (!v) return null;
  const t = Date.parse(String(v).replace(" ", "T").replace(/(\.\d{3})\d+/, "$1"));
  return Number.isNaN(t) ? null : t;
}

export const useAlertStore = defineStore("alerts", {
  state: () => ({
    alerts: [],
    // true setelah daftar alarm dari server berhasil dimuat sekali. Alarm yang sudah ada saat itu = "alarm lama".
    loaded: false,
  }),
  actions: {
    // Gabungkan daftar server ke state tanpa menimpa alarm yang baru masuk lewat SSE.
    // Alarm lama (sudah ada waktu dashboard dibuka) tidak ditandai _live -> tampil, tapi tanpa bunyi/notifikasi.
    // Alarm yang baru ketahuan SETELAH muat awal (SSE sempat putus) ditandai _live -> dibunyikan.
    mergeFromServer(list) {
      if (!Array.isArray(list)) return;
      const have = new Set(this.alerts.map((a) => a.id));
      const missing = list.filter((a) => !have.has(a.id) && !acked.has(a.id));
      if (this.loaded) {
        this.alerts = [...missing.map((a) => ({ ...a, _live: true })), ...this.alerts];
      } else {
        this.alerts = [...this.alerts, ...missing];
        this.loaded = true;
      }
    },
    async loadInitial() {
      this.mergeFromServer(await fetchAlerts());
    },
    // Dipanggil berkala oleh SosOverlay sebagai jaring pengaman bila ada siaran SSE yang terlewat.
    async sync() {
      try {
        this.mergeFromServer(await fetchAlerts());
      } catch (e) {
        /* backend sedang restart: coba lagi di putaran berikutnya */
      }
    },
    // Dipanggil HANYA dari stream SSE (alarm yang benar-benar baru terjadi).
    addAlert(alert) {
      if (this.alerts.some((a) => a.id === alert.id) || acked.has(alert.id)) return;
      this.alerts.unshift({ ...alert, _live: true });
    },
    removeBySession(sessionId) {
      this.alerts = this.alerts.filter((a) => a.session_id !== sessionId);
    },
    // SOS dibatalkan dari alat: payload posisi TERBARU pendaki membawa sos=false -> kartu SOS otomatis hilang.
    // Hanya alarm MANUAL_SOS (yang dipicu tombol SOS) yang ikut, dan hanya oleh paket yang DITERIMA SETELAH
    // alarm dibuat (paket telat/lama tidak boleh membatalkan SOS baru). Kalau waktu tidak terbaca -> alarm
    // dibiarkan tampil (aman). Server ikut ditandai ACKNOWLEDGED supaya sync 10 detik tidak memunculkannya lagi
    // dan tekanan SOS berikutnya dibuatkan alarm baru oleh backend.
    cancelBySosFlag(hikers) {
      for (const a of [...this.alerts]) {
        if (a.alert_type !== "MANUAL_SOS") continue;
        const h = hikers?.[a.hiker_code];
        if (!h || !("sos" in h) || h.sos) continue; // belum ada paket live, atau SOS masih menyala
        if (a.session_id != null && h.session_id != null && a.session_id !== h.session_id) continue;
        const sentAt = toMs(h.received_at);
        const raisedAt = toMs(a.triggered_at);
        if (sentAt == null || raisedAt == null || sentAt <= raisedAt) continue;
        acked.add(a.id);
        this.alerts = this.alerts.filter((x) => x.id !== a.id);
        acknowledgeAlert(a.id).catch(() => {});
      }
    },
    async acknowledge(alertId) {
      acked.add(alertId);
      await acknowledgeAlert(alertId);
      this.alerts = this.alerts.filter((a) => a.id !== alertId);
    },
  },
});