import { defineStore } from "pinia";
import { fetchLatestPositions, fetchHikerTrack } from "../services/api";

export const useHikerStore = defineStore("hikers", {
  state: () => ({
    hikers: {}, // keyed by hiker_code
    tracks: {}, // keyed by hiker_code -> [[lat, lon], ...] urut waktu (jejak yang udah dilalui)
    selectedCode: null, // hiker yang lagi dipilih monitor - dipakai bareng MapView & MonitoringPanel
  }),
  actions: {
    async loadInitial() {
      const positions = await fetchLatestPositions();
      for (const p of positions) {
        this.hikers[p.hiker_code] = p;
      }
      // Ambil jejak historis tiap pendaki sekali di awal. Update
      // selanjutnya (posisi baru dari SSE) tinggal nambah ke array yang
      // sudah ada lewat applyPositionUpdate, gak perlu fetch ulang.
      await Promise.all(
        positions.map(async (p) => {
          try {
            const track = await fetchHikerTrack(p.hiker_code);
            this.tracks[p.hiker_code] = track
              .filter((t) => t.lat != null && t.lon != null)
              .map((t) => [t.lat, t.lon]);
          } catch (e) {
            this.tracks[p.hiker_code] = [];
          }
        })
      );
    },
    applyPositionUpdate(data) {
      // Alat yang sama dipakai pendaki lain (sesi berganti) -> jejak mulai dari nol.
      const prev = this.hikers[data.hiker_code];
      if (prev && data.session_id != null && prev.session_id != null && prev.session_id !== data.session_id) {
        this.tracks[data.hiker_code] = [];
      }
      // Paket tanpa fix datang dengan lat/lon null: pertahankan lokasi terakhir (last known), jangan ditimpa.
      const { lat, lon, elevation, ...rest } = data;
      const hasFix = lat != null && lon != null;
      this.hikers[data.hiker_code] = { ...this.hikers[data.hiker_code], ...rest, ...(hasFix ? { lat, lon, elevation } : {}) };
      if (data.lat != null && data.lon != null) {
        const arr = this.tracks[data.hiker_code] || (this.tracks[data.hiker_code] = []);
        const last = arr[arr.length - 1];
        if (!last || last[0] !== data.lat || last[1] !== data.lon) {
          arr.push([data.lat, data.lon]);
        }
      }
    },
    // Sesi di-check-out: alatnya hilang dari peta & daftar monitoring (jejak ada di riwayat).
    removeHiker(code) {
      delete this.hikers[code];
      delete this.tracks[code];
      if (this.selectedCode === code) this.selectedCode = null;
    },
    // Dipanggil dari list di MonitoringPanel ATAU dari klik marker di
    // MapView - satu sumber kebenaran buat "siapa yang lagi dipilih".
    // Klik yang sama dua kali = unselect (toggle).
    selectHiker(code) {
      this.selectedCode = this.selectedCode === code ? null : code;
    },
    clearSelection() {
      this.selectedCode = null;
    },
  },
});