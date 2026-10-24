import { defineStore } from "pinia";

// Mode tampilan. Harian (bawaan) = peta, daftar pendaki, check-in, alarm.
// Lanjutan = ditambah diagnostik link, grafik RSSI, Setup lokasi/DEM/relay, data & cadangan.
// Murni pengaturan tampilan (disimpan di browser); tidak mengubah data atau perilaku backend.
const KEY = "silacak.advanced";
function read() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch (e) {
    return false;
  }
}

export const useUiStore = defineStore("ui", {
  state: () => ({ advanced: read() }),
  actions: {
    setAdvanced(v) {
      this.advanced = !!v;
      try {
        localStorage.setItem(KEY, this.advanced ? "1" : "0");
      } catch (e) {
        /* mode tetap berlaku selama halaman terbuka */
      }
    },
    toggleAdvanced() {
      this.setAdvanced(!this.advanced);
    },
  },
});
