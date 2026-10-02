import { defineStore } from "pinia";
import { fetchActiveSite, uploadDem, saveSiteInputs, computeRelayPlan, dismissFailedUpload, saveRelayPositions } from "../services/api";

export const useSiteStore = defineStore("site", {
  state: () => ({
    site: null, // lokasi aktif dari backend (DEM + base + trail + hasil relay)
    showSetup: false,
    editMode: null, // null | "base" | "trail" -> klik peta buat nambah titik
    busy: false, // upload / hitung lagi jalan
    error: null,
    _timer: null,
    _planTimer: null,
  }),
  getters: {
    ready: (s) => s.site?.status === "ready",
    // "processing" = DEM pertama lagi diproses, ATAU DEM pengganti lagi diproses (DEM lama tetap aktif)
    processing: (s) => s.site?.status === "processing" || s.site?.pending?.status === "processing",
    pendingError: (s) => (s.site?.pending?.status === "error" ? s.site.pending.message : null),
  },
  actions: {
    async loadActive() {
      try {
        const prevId = this.site?.id;
        const wasProcessing = this.processing;
        this.site = await fetchActiveSite();
        if (this.processing) this.poll();
        // lokasi lama yang topo-nya baru dibuat di background saat backend start: cek tiap 5 dtk (maks ~5 menit)
        else if (this.site?.status === "ready" && !this.site.dem_info?.topo && (this._topoPolls = (this._topoPolls || 0) + 1) <= 60)
          setTimeout(() => this.loadActive(), 5000);
        // begitu selesai (DEM pertama maupun pengganti), plan otomatis dihitung backend
        // beberapa detik kemudian -> ambil sekali lagi
        else if (wasProcessing || (prevId && this.site?.id !== prevId)) setTimeout(() => this.loadActive(), 2500);
      } catch (e) {
        this.error = e.message;
      }
    },
    poll() {
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.loadActive(), 2000);
    },
    async dismissError() {
      await dismissFailedUpload().catch(() => {});
      await this.loadActive();
    },
    async upload(file, name) {
      this.error = null;
      this.busy = true;
      try {
        await uploadDem(file, name);
        await this.loadActive(); // status "processing" -> polling jalan sendiri
      } catch (e) {
        this.error = e.message;
      } finally {
        this.busy = false;
      }
    },
    inBounds(lat, lon) {
      const b = this.site?.dem_info?.bounds;
      return !!b && lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3];
    },
    async handleMapClick(lat, lon) {
      if (!this.site || !this.inBounds(lat, lon)) {
        this.error = "Titik di luar cakupan DEM.";
        return;
      }
      this.error = null;
      const r = (v) => Math.round(v * 1e6) / 1e6;
      if (this.editMode === "base") {
        this.site.base = { lat: r(lat), lon: r(lon) };
        this.editMode = null;
      } else if (this.editMode === "trail") {
        this.site.trail = [...this.site.trail, [r(lat), r(lon)]];
      }
      await this.saveInputs();
    },
    async saveInputs({ auto = true } = {}) {
      try {
        const s = await saveSiteInputs({ base: this.site.base, trail: this.site.trail, params: this.site.params });
        this.site = s;
      } catch (e) {
        this.error = e.message;
        return;
      }
      // Rencana relay dihitung otomatis begitu base + min. 2 titik trail ada
      // (ditunda sebentar biar gambar trail banyak klik nggak memicu hitung berkali-kali).
      clearTimeout(this._planTimer);
      // Plan hasil geseran manual dipertahankan (backend menilainya ulang di tempat); hanya tombol "Hitung ulang" yang membuangnya.
      if (auto && this.site.base && this.site.trail.length >= 2 && !this.site.plan?.manual) {
        this._planTimer = setTimeout(() => this.runPlan(), 1200);
      }
    },
    // Relay digeser di peta (Setup aktif). Posisi baru disimpan & tiap link dinilai ulang dari DEM.
    async moveRelay(n, lat, lon) {
      const snapBack = () => { this.site = { ...this.site }; }; // paksa peta menggambar ulang posisi sah terakhir
      if (!this.inBounds(lat, lon)) {
        this.error = "Relay di luar cakupan DEM.";
        return snapBack();
      }
      const r = (v) => Math.round(v * 1e6) / 1e6;
      const relays = (this.site.plan?.relays || []).map((x) => (x.n === n ? [r(lat), r(lon)] : [x.lat, x.lon]));
      try {
        this.error = null;
        const plan = await saveRelayPositions(relays);
        this.site = { ...this.site, plan };
      } catch (e) {
        this.error = e.message;
        snapBack();
      }
    },
    async undoTrail() {
      this.site.trail = this.site.trail.slice(0, -1);
      await this.saveInputs();
    },
    async clearTrail() {
      this.site.trail = [];
      await this.saveInputs();
    },
    async runPlan() {
      this.error = null;
      this.busy = true;
      try {
        const plan = await computeRelayPlan();
        this.site = { ...this.site, plan };
      } catch (e) {
        this.error = e.message;
      } finally {
        this.busy = false;
      }
    },
  },
});