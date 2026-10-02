import { defineStore } from "pinia";
import { fetchDiagnostics, fetchPackets } from "../services/api";

// Diagnostik link per sesi aktif (PDR, latency, node basi, jarak ke base) + packet log pendaki terpilih.
// Polling ringan: dashboard lokal, dan indikator "basi" memang perlu dihitung ulang berkala.
export const useDiagnosticsStore = defineStore("diagnostics", {
  state: () => ({ sessions: {}, staleAfterS: 120, baseSet: false, packets: [], packetsFor: null }),
  getters: {
    list: (s) => Object.values(s.sessions).sort((a, b) => a.hiker_code.localeCompare(b.hiker_code)),
    // PDR gabungan semua sesi aktif: total diterima / (diterima + hilang), paket pertama tiap sesi = jangkar.
    pdrOverall() {
      let got = 0, lost = 0;
      for (const d of this.list) { got += Math.max(d.received - 1, 0); lost += d.missing; }
      return got + lost > 0 ? (100 * got) / (got + lost) : null;
    },
    latencyMedianS() {
      const v = this.list.map((d) => d.latency_p50_s).filter((x) => x != null).sort((a, b) => a - b);
      return v.length ? v[Math.floor(v.length / 2)] : null;
    },
  },
  actions: {
    async refresh(selectedCode) {
      try {
        const d = await fetchDiagnostics();
        this.staleAfterS = d.stale_after_s;
        this.baseSet = d.base_set;
        this.sessions = Object.fromEntries(d.sessions.map((x) => [x.hiker_code, x]));
        if (selectedCode) {
          this.packets = await fetchPackets(selectedCode);
          this.packetsFor = selectedCode;
        } else {
          this.packets = [];
        }
      } catch (e) {
        /* backend sedang restart: coba lagi di tick berikutnya */
      }
    },
  },
});
