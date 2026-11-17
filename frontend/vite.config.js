import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      // halaman pengaturan milik backend (dipakai juga oleh jendela Pengaturan di dalam dashboard)
      "/pengaturan": "http://localhost:8000",
      "/awal": "http://localhost:8000",
    },
  },
});
