import { defineStore } from "pinia";
import { acknowledgeAlert, fetchAlerts } from "../services/api";

export const useAlertStore = defineStore("alerts", {
  state: () => ({
    alerts: [],
  }),
  actions: {
    async loadInitial() {
      this.alerts = await fetchAlerts();
    },
    addAlert(alert) {
      this.alerts.unshift(alert);
    },
    removeBySession(sessionId) {
      this.alerts = this.alerts.filter((a) => a.session_id !== sessionId);
    },
    async acknowledge(alertId) {
      await acknowledgeAlert(alertId);
      this.alerts = this.alerts.filter((a) => a.id !== alertId);
    },
  },
});
