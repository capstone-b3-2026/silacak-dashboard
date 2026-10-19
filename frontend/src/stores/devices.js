import { defineStore } from "pinia";
import { fetchDevices, createDevice, updateDevice, deleteDevice, pushDevice, setDevicePlanSlot } from "../services/api";

export const useDeviceStore = defineStore("devices", {
  state: () => ({ devices: [], error: null, busy: false, _timer: null }),
  getters: {
    outOfSync: (s) => s.devices.filter((d) => !d.in_sync),
    inFlight: (s) => s.devices.some((d) => ["pending", "sent"].includes(d.last_command?.status)),
  },
  actions: {
    async load() {
      try {
        this.devices = await fetchDevices();
        this.error = null;
      } catch (e) {
        this.error = e.message;
      }
      // selama ada perintah yang belum dikonfirmasi alat, cek status tiap 3 dtk
      clearTimeout(this._timer);
      if (this.inFlight) this._timer = setTimeout(() => this.load(), 3000);
    },
    // Muat sekali TANPA polling. Dipakai peta (pemetaan relay untuk rute). load() menjadwalkan ulang tiap 3 dtk selama ada
    // perintah yang belum dikonfirmasi alat, sehingga kalau dipakai peta, polling jalan terus walau panel Setup tertutup.
    async refresh() {
      try {
        this.devices = await fetchDevices();
        this.error = null;
      } catch (e) {
        this.error = e.message;
      }
    },
    async _run(fn) {
      this.busy = true;
      this.error = null;
      try {
        this.devices = await fn();
      } catch (e) {
        this.error = e.message;
        return false;
      } finally {
        this.busy = false;
      }
      if (this.inFlight) this.load();
      return true;
    },
    save(form, id = null) {
      const body = { node_id: Number(form.node_id), name: form.name, role: form.role, config: form.config };
      return this._run(() => (id ? updateDevice(id, body) : createDevice(body)));
    },
    setSlot(id, slot) {
      return this._run(() => setDevicePlanSlot(id, slot));
    },
    remove(id) {
      return this._run(() => deleteDevice(id));
    },
    push(id) {
      return this._run(() => pushDevice(id));
    },
    async pushAll() {
      for (const d of this.outOfSync) await this._run(() => pushDevice(d.id));
    },
    stop() {
      clearTimeout(this._timer);
    },
  },
});