import { defineStore } from "pinia";
import { fetchRelayStatus } from "../services/api";

// Batas "baterai rendah" untuk lencana. Hanya penanda peringatan (amber); merah dipakai khusus SOS.
export const RELAY_LOW_PCT = 20;
// Relay melapor ~tiap 30 dtk; 120 dtk tanpa laporan = tidak terdengar (sama dengan `stale` di backend).
export const RELAY_STALE_MS = 120000;

// Baterai relay: hanya MEMBACA /relays/status berkala. Kosong = belum ada laporan (relay belum menyala,
// atau data masuk lewat bridge luar yang belum membaca baris CSV_RELAY_BATTERY).
export const useRelayStore = defineStore("relays", {
  state: () => ({ items: [], fetchedAt: Date.now(), error: null, _poll: null }),
  actions: {
    async refresh() {
      try {
        this.items = await fetchRelayStatus();
        this.fetchedAt = Date.now();
        this.error = null;
      } catch (e) {
        this.error = e.message;
      }
    },
    start() {
      if (this._poll) return;
      this.refresh();
      this._poll = setInterval(() => this.refresh(), 5000);
    },
    stop() {
      clearInterval(this._poll);
      this._poll = null;
    },
  },
});
