import { defineStore } from "pinia";
import { fetchBasePorts, fetchBaseStatus, selectBasePort } from "../services/api";

// Status base station (USB serial) untuk lencana di dashboard. Hanya MEMBACA /base/status berkala;
// satu-satunya aksi tulis adalah memilih port (POST /base/port) lewat tombol "Pilih port".
export const useBaseStore = defineStore("base", {
  state: () => ({
    status: null, // respons GET /base/status
    unreachable: false, // true = backend tidak menjawab
    ports: [],
    portsLoading: false,
    error: null,
    now: Date.now(), // detak 1 dtk supaya "paket terakhir X detik lalu" jalan sendiri
    _poll: null,
    _tick: null,
  }),
  actions: {
    async refresh() {
      try {
        this.status = await fetchBaseStatus();
        this.unreachable = false;
      } catch (e) {
        this.unreachable = true;
      }
    },
    start() {
      if (this._poll) return;
      this.refresh();
      this._poll = setInterval(() => this.refresh(), 3000);
      this._tick = setInterval(() => (this.now = Date.now()), 1000);
    },
    stop() {
      clearInterval(this._poll);
      clearInterval(this._tick);
      this._poll = this._tick = null;
    },
    async loadPorts() {
      this.portsLoading = true;
      this.error = null;
      try {
        this.ports = await fetchBasePorts();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.portsLoading = false;
      }
    },
    async choosePort(port) {
      this.error = null;
      try {
        this.status = await selectBasePort(port);
        return true;
      } catch (e) {
        this.error = e.message;
        return false;
      }
    },
  },
});
