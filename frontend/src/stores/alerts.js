import { defineStore } from "pinia";
import { acknowledgeAlert, fetchAlerts } from "../services/api";

// Alarm yang sudah ditandai "Sudah ditangani" di browser ini. Mencegah respons /alerts yang masih dalam
// perjalanan (diminta sebelum tombol ditekan) memunculkan lagi alarm tersebut + bunyi ulang.
const acked = new Set();

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
    async acknowledge(alertId) {
      acked.add(alertId);
      await acknowledgeAlert(alertId);
      this.alerts = this.alerts.filter((a) => a.id !== alertId);
    },
  },
});