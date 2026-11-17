import { defineStore } from "pinia";
import { nextTick } from "vue";
import { PROBE_MAX, makeSample, summarize, toCsv } from "../utils/latencyProbe";

// Mencatat waktu tiba SSE dan waktu layar selesai diperbarui untuk tiap paket posisi (pengukuran latensi ujung ke ujung
// sisi browser). Hanya di memori (maks. PROBE_MAX paket terakhir); CSV-nya bisa diunduh untuk laporan.
export const useLatencyProbeStore = defineStore("latencyProbe", {
  state: () => ({ samples: [] }),
  getters: {
    summary: (s) => summarize(s.samples),
    count: (s) => s.samples.length,
  },
  actions: {
    add(sample) {
      this.samples.push(sample);
      if (this.samples.length > PROBE_MAX) this.samples.splice(0, this.samples.length - PROBE_MAX);
    },
    // tSse = waktu SSE tiba (epoch ms, dicatat paling awal di handler EventSource). "Tergambar" = Vue selesai memperbarui DOM
    // (nextTick), satu frame dicat (requestAnimationFrame), lalu sesudah pengecatan (setTimeout 0).
    sampleAfterRender(data, tSse) {
      // Tab/jendela di latar: requestAnimationFrame ditahan browser, hasilnya menggelembung. Jangan dicatat.
      if (typeof document !== "undefined" && document.hidden) return;
      nextTick(() => requestAnimationFrame(() => setTimeout(() => this.add(makeSample(data, tSse, Date.now())), 0)));
    },
    csv() {
      return toCsv(this.samples);
    },
    clear() {
      this.samples = [];
    },
  },
});
