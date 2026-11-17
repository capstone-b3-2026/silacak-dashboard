import { defineStore } from "pinia";
import {
  fetchActiveSite, uploadDem, saveSiteInputs, computeRelayPlan, dismissFailedUpload, saveRelayPositions,
  uploadCanopy, deleteCanopy, fetchCalibration, fetchTrailDistance3d,
} from "../services/api";
import { withAdded, withMoved, withRemoved } from "../utils/relayEdit";

export const useSiteStore = defineStore("site", {
  state: () => ({
    site: null, // lokasi aktif dari backend (DEM + base + trail + hasil relay)
    showSetup: false,
    editMode: null, // null | "base" | "trail" | "relay" -> klik peta buat nambah titik / relay
    busy: false, // upload / hitung lagi jalan
    calibration: null, // hasil GET /sites/active/calibration (saran offset & margin fading)
    calibrating: false,
    error: null,
    trail3d: null, // hasil POST /sites/active/trail-distance (profil 3D dari DEM); null = belum/tak tersedia
    _timer: null,
    _planTimer: null,
    _trail3dTimer: null,
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
    // Data kanopi berubah -> rencana lama basi: simpan ulang input (backend menilai ulang posisi manual / hitung otomatis)
    async uploadCanopyFile(file) {
      this.error = null;
      this.busy = true;
      try {
        await uploadCanopy(file);
        await this.loadActive();
      } catch (e) {
        this.error = e.message;
        return;
      } finally {
        this.busy = false;
      }
      await this.saveInputs();
    },
    async removeCanopy() {
      this.busy = true;
      try {
        await deleteCanopy();
        await this.loadActive();
      } catch (e) {
        this.error = e.message;
        return;
      } finally {
        this.busy = false;
      }
      await this.saveInputs();
    },
    async calibrate({ maxKm = null } = {}) {
      this.error = null;
      this.calibrating = true;
      try {
        this.calibration = await fetchCalibration({ maxKm });
      } catch (e) {
        this.error = e.message;
      } finally {
        this.calibrating = false;
      }
    },
    async applyCalibration() {
      const c = this.calibration;
      if (!c?.reliable) return;
      this.site.params.calib_offset_db = c.suggested_calib_offset_db;
      if (c.suggested_fade_margin_db != null) this.site.params.fade_margin_db = c.suggested_fade_margin_db;
      this.calibration = null; // sudah dipakai; hitung ulang untuk memeriksa (bias harus ~0)
      await this.saveInputs();
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
      } else if (this.editMode === "relay") {
        // Mode tetap menyala supaya operator bisa menaruh beberapa relay berturut-turut; matikan lewat tombolnya.
        return this.addRelay(lat, lon);
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
      // Angka 3D (profil dari DEM) hanya BONUS/sekunder: hitung dengan cadence ringan (debounce) supaya
      // menggambar banyak titik tidak membanjiri backend. Angka horizontal (FEAT-001) sudah tampil instan
      // dari helper murni di frontend tanpa menunggu ini.
      this.refreshTrail3d();
    },
    // Ambil jarak 3D profil dari DEM, DEBOUNCED (800 ms). Hanya saat DEM siap & base + >= 2 titik trail.
    // Error jaringan ditelan rapi (trail3d = null) supaya tidak mengganggu angka horizontal.
    refreshTrail3d() {
      clearTimeout(this._trail3dTimer);
      const ok = this.site?.status === "ready" && this.site?.base && (this.site?.trail?.length || 0) >= 2;
      if (!ok) {
        this.trail3d = null;
        return;
      }
      const payload = { base: this.site.base, trail: this.site.trail };
      this._trail3dTimer = setTimeout(async () => {
        try {
          this.trail3d = await fetchTrailDistance3d(payload);
        } catch {
          this.trail3d = null;
        }
      }, 800);
    },
    // Penyuntingan relay oleh operator: geser, tambah, hapus, atau kosongkan, TANPA menunggu saran perencana.
    // Daftar baru disimpan lalu tiap link dinilai ulang dari DEM (plan hasilnya bertanda manual).
    async _saveRelays(list) {
      try {
        this.error = null;
        const plan = await saveRelayPositions(list);
        this.site = { ...this.site, plan };
        return true;
      } catch (e) {
        this.error = e.message;
        this.site = { ...this.site }; // paksa peta menggambar ulang posisi sah terakhir
        return false;
      }
    },
    _relayEditReady() {
      if (!this.site?.base || !(this.site?.trail?.length >= 1)) {
        this.error = "Isi titik base dan jalur dulu sebelum menaruh relay.";
        return false;
      }
      if (this.site.status !== "ready") {
        this.error = "DEM belum siap.";
        return false;
      }
      return true;
    },
    // Relay digeser di peta (Setup aktif). Posisi baru disimpan & tiap link dinilai ulang dari DEM.
    async moveRelay(n, lat, lon) {
      if (!this.inBounds(lat, lon)) {
        this.error = "Relay di luar cakupan DEM.";
        this.site = { ...this.site };
        return;
      }
      await this._saveRelays(withMoved(this.site.plan, n, lat, lon));
    },
    async addRelay(lat, lon) {
      if (!this._relayEditReady()) return;
      if (!this.inBounds(lat, lon)) {
        this.error = "Relay di luar cakupan DEM.";
        return;
      }
      try {
        await this._saveRelays(withAdded(this.site.plan, lat, lon));
      } catch (e) {
        this.error = e.message; // batas jumlah relay
      }
    },
    async removeRelay(n) {
      if (!this._relayEditReady()) return false;
      return this._saveRelays(withRemoved(this.site.plan, n)); // true bila tersimpan
    },
    // "Tanpa relay": hanya base yang dihitung (cakupan = apa yang terjangkau langsung dari base).
    async clearRelays() {
      if (!this._relayEditReady()) return;
      await this._saveRelays([]);
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