<template>
  <div class="sos-stack">
    <button v-if="alertStore.alerts.length > 1" class="sos-ack-all" @click="acknowledgeAll">
      Acknowledge semua ({{ alertStore.alerts.length }})
    </button>
    <transition-group name="drop" tag="div" class="sos-list">
      <div v-for="a in alertStore.alerts" :key="a.id" class="sos-card" role="alert">
        <span class="sos-icon">🆘</span>
        <div class="sos-text">
          <strong>{{ a.hiker_code || "?" }} — SOS</strong>
          <span>{{ alertLabel(a.alert_type) }} · {{ fmtTime(a.triggered_at) }}</span>
        </div>
        <button class="sos-ack" @click="alertStore.acknowledge(a.id)">Acknowledge</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { watch } from "vue";
import { useAlertStore } from "../stores/alerts";

const alertStore = useAlertStore();

const ALERT_LABELS = {
  STAGNANT: "diam di tempat",
  MANUAL_SOS: "SOS manual",
  LOW_BATTERY: "baterai kritis",
};
function alertLabel(type) {
  return ALERT_LABELS[type] || type?.toLowerCase() || "tidak diketahui";
}
function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

// Minta izin notifikasi browser sekali di awal. Kalau ditolak/gak
// didukung ya gapapa, overlay + bunyi di bawah tetap jalan sebagai
// fallback (overlay ini gak bergantung sama Notification API).
if (typeof Notification !== "undefined" && Notification.permission === "default") {
  Notification.requestPermission();
}

let knownIds = new Set();
let audioCtx = null;

function beep() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();

    // Pola Morse SOS asli: ...  ---  ... (titik-titik-titik,
    // garis-garis-garis, titik-titik-titik) - lebih dikenal sebagai bunyi
    // darurat daripada sekadar beep generik. Dijadwalkan lewat
    // audioCtx.currentTime (bukan setTimeout bertingkat) biar timingnya
    // presisi dan gak nge-drift.
    const DOT = 0.13; // detik
    const DASH = DOT * 3;
    const GAP = DOT; // jeda antar titik/garis dalam satu huruf
    const LETTER_GAP = DOT * 3; // jeda antar huruf S - O - S
    const FREQ = 900;

    function tone(startAt, duration) {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = "square";
      o.frequency.value = FREQ;
      g.gain.value = 0.18;
      o.connect(g);
      g.connect(audioCtx.destination);
      o.start(startAt);
      o.stop(startAt + duration);
    }

    const pattern = [DOT, DOT, DOT, DASH, DASH, DASH, DOT, DOT, DOT];
    let t = audioCtx.currentTime + 0.05;
    pattern.forEach((dur, i) => {
      tone(t, dur);
      t += dur + GAP;
      if (i === 2 || i === 5) t += LETTER_GAP - GAP; // jeda ekstra antar huruf
    });
  } catch (e) {
    // browser block autoplay audio kalau belum ada interaksi user -
    // overlay visual tetap muncul walau bunyinya gagal.
  }
}

function notifyBrowser(alert) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification("🆘 SOS AKTIF", {
    body: `${alert.hiker_code || "?"} — ${alertLabel(alert.alert_type)}`,
    requireInteraction: true,
  });
}

// Trigger beep + notifikasi cuma buat alert yang BENERAN baru masuk,
// bukan tiap kali array alerts berubah (misal pas ada yang di-acknowledge).
watch(
  () => alertStore.alerts,
  (alerts) => {
    for (const a of alerts) {
      if (!knownIds.has(a.id)) {
        beep();
        notifyBrowser(a);
      }
    }
    knownIds = new Set(alerts.map((a) => a.id));
  },
  { deep: true, immediate: true }
);

function acknowledgeAll() {
  [...alertStore.alerts].forEach((a) => alertStore.acknowledge(a.id));
}
</script>

<style scoped>
.sos-stack {
  position: fixed;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  pointer-events: none;
}
.sos-list { display: flex; flex-direction: column; gap: 8px; align-items: center; }

.sos-ack-all {
  pointer-events: auto;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}
.sos-ack-all:hover { background: rgba(0, 0, 0, 0.7); }

.sos-card {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 14px;
  background: #c43a3a;
  color: #fff;
  border-radius: 12px;
  padding: 9px 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: sos-pulse 1.2s ease-in-out infinite;
  min-width: 260px;
}
.sos-icon { font-size: 19px; flex-shrink: 0; }
.sos-text { display: flex; flex-direction: column; font-size: 11.5px; flex: 1; min-width: 0; }
.sos-text strong { font-size: 13.5px; letter-spacing: 0.02em; }
.sos-text span { opacity: 0.9; text-transform: capitalize; }
.sos-ack {
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.4);
  color: #fff;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 11.5px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.sos-ack:hover { background: rgba(255, 255, 255, 0.3); }
@keyframes sos-pulse {
  0%, 100% { box-shadow: 0 8px 24px rgba(196, 58, 58, 0.4); }
  50% { box-shadow: 0 8px 34px rgba(196, 58, 58, 0.75); }
}
.drop-enter-active, .drop-leave-active { transition: all 0.25s ease; }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-16px); }
.drop-move { transition: transform 0.25s ease; }
</style>