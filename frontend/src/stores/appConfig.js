import { defineStore } from "pinia";
import { fetchAppConfig } from "../services/api";
import { DEFAULT_PERIMETER_M, perimeterFromConfig } from "../utils/appConfig";

export const useAppConfigStore = defineStore("appConfig", {
  state: () => ({
    perimeterM: DEFAULT_PERIMETER_M,
    loaded: false, // false = masih memakai bawaan sementara
    error: null,
  }),
  actions: {
    // Dipanggil saat dashboard mulai dan setiap kali halaman pengaturan menyimpan.
    async load() {
      try {
        const p = perimeterFromConfig(await fetchAppConfig());
        if (p != null) {
          this.perimeterM = p;
          this.loaded = true;
        }
        this.error = null;
      } catch (e) {
        this.error = e.message; // peta tetap memakai nilai terakhir yang diketahui
      }
    },
  },
});
