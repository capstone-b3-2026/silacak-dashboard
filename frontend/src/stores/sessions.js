import { defineStore } from "pinia";
import { checkInSession, checkOutSession, fetchSessions } from "../services/api";

export const useSessionStore = defineStore("sessions", {
  state: () => ({
    active: [], // sesi berjalan, urut check-in
    history: [], // sesi selesai, terbaru dulu (dimuat saat Riwayat dibuka)
  }),
  getters: {
    // sesi yang dibuka otomatis karena alat mengirim data tanpa check-in
    unregistered: (s) => s.active.filter((x) => x.auto_opened),
  },
  actions: {
    async loadActive() {
      this.active = await fetchSessions("active");
    },
    async loadHistory() {
      this.history = await fetchSessions("completed");
    },
    async checkIn(payload) {
      const s = await checkInSession(payload);
      this.applyEvent("opened", s); // SSE juga akan datang; applyEvent idempoten
      return s;
    },
    async checkOut(sessionId) {
      const s = await checkOutSession(sessionId);
      this.applyEvent("closed", s);
      return s;
    },
    applyEvent(event, session) {
      const i = this.active.findIndex((x) => x.id === session.id);
      if (event === "closed") {
        if (i >= 0) this.active.splice(i, 1);
        this.history = [session, ...this.history.filter((x) => x.id !== session.id)];
      } else if (i >= 0) {
        this.active[i] = { ...this.active[i], ...session };
      } else {
        this.active.push(session);
      }
    },
  },
});
