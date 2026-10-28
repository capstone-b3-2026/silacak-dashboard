<template>
  <div class="sos-stack">
    <div v-if="sosAlerts.length" class="sos-pill" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 16.5h.01" /></svg>
      {{ sosAlerts.length }} alarm SOS perlu ditangani
    </div>
    <button v-if="sosAlerts.length > 1" class="sos-ack-all" @click="acknowledgeAll">
      Tandai semua sudah ditangani ({{ sosAlerts.length }})
    </button>
    <!-- suara diblokir browser: alarm tampil visual saja sampai tombol ini ditekan -->
    <button v-if="alarmActive && !sound.enabled" class="sos-sound" @click="enableSound">
      Suara alarm diblokir browser. Klik di sini untuk mengaktifkan
    </button>
    <transition-group name="drop" tag="div" class="sos-list">
      <div v-for="a in sosAlerts" :key="a.id" class="sos-card" role="alert">
        <span class="sos-icon">SOS</span>
        <div class="sos-text">
          <strong>{{ a.hiker_code || "?" }} — SOS</strong>
          <span>{{ alertLabel(a.alert_type) }} · {{ fmtTime(a.triggered_at) }}</span>
        </div>
        <button class="sos-ack" @click="alertStore.acknowledge(a.id)">Sudah ditangani</button>
      </div>
    </transition-group>

    <!-- "di luar jalur" (OFF_TRAIL): peringatan AMBER, bukan SOS merah, dan TIDAK bisa disenyapkan manual
         (hilang sendiri saat pendaki kembali masuk perimeter). Ditampilkan seperti kartu "tidak terdengar". -->
    <transition-group name="drop" tag="div" class="sos-list">
      <div v-for="a in offTrailAlerts" :key="`offtrail-${a.id}`" class="sos-card warn" role="alert">
        <span class="sos-icon">Jalur</span>
        <div class="sos-text">
          <strong>{{ a.hiker_code || "?" }} — di luar jalur</strong>
          <span>Keluar perimeter<template v-if="a.meta?.dist_to_trail_m != null"> · {{ Math.round(a.meta.dist_to_trail_m) }} m dari jalur</template>. Pantau dan hubungi pendaki.</span>
        </div>
        <button class="sos-ack" @click="hikerStore.selectHiker(a.hiker_code)">Lihat</button>
      </div>
    </transition-group>

    <!-- node tidak terdengar: dihitung dari diagnostik link (data yang sudah ada), bukan alarm baru di backend -->
    <transition-group name="drop" tag="div" class="sos-list">
      <div v-for="n in silentNodes" :key="`silent-${n.hiker_code}`" class="sos-card warn" role="alert">
        <span class="sos-icon">Sinyal</span>
        <div class="sos-text">
          <strong>{{ n.hiker_code }} — tidak terdengar</strong>
          <span>Tidak ada paket sejak {{ fmtAge(n.silent_s) }}. Cek posisi terakhir &amp; hubungi pendaki.</span>
        </div>
        <button class="sos-ack" @click="hikerStore.selectHiker(n.hiker_code)">Lihat</button>
        <button class="sos-ack" @click="muteSilent(n.hiker_code)" title="Sembunyikan sampai alat ini terdengar lagi">Senyapkan</button>
      </div>
    </transition-group>

    <!-- baterai rendah: aktif otomatis begitu firmware mengirim battery_pct (sekarang masih kosong) -->
    <transition-group name="drop" tag="div" class="sos-list">
      <div v-for="b in lowBattery" :key="`bat-${b.code}`" class="sos-card warn" role="alert">
        <span class="sos-icon">Baterai</span>
        <div class="sos-text">
          <strong>{{ b.code }} — baterai rendah ({{ Math.round(b.pct) }}%)</strong>
          <span>Minta pendaki menghemat daya atau turun.</span>
        </div>
        <button class="sos-ack" @click="hikerStore.selectHiker(b.code)">Lihat</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, watch } from "vue";
import { useAlertStore } from "../stores/alerts";
import { useHikerStore } from "../stores/hikers";
import { useDiagnosticsStore } from "../stores/diagnostics";
import { enableSound, play, sound } from "../composables/useAlarmSound";
import { alertLabel } from "../utils/alerts";

const alertStore = useAlertStore();
const hikerStore = useHikerStore();
const diagStore = useDiagnosticsStore();
// Hanya alarm SOS (merah) yang memicu pil/kartu merah, bunyi, dan notifikasi. OFF_TRAIL (amber) dipisah:
// merah = SOS saja (lihat .kiro/steering/conventions.md). OFF_TRAIL tampil amber, tanpa bunyi SOS.
const sosAlerts = computed(() => alertStore.alerts.filter((a) => a.alert_type !== "OFF_TRAIL"));
const offTrailAlerts = computed(() => alertStore.alerts.filter((a) => a.alert_type === "OFF_TRAIL"));
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

// Pola Morse SOS (... --- ...) sama persis seperti sebelumnya, kini lewat pemutar bersama (useAlarmSound)
// yang memanggil resume() dan melacak status "suara aktif / diblokir".
function beep() {
  play("sos");
}

function notifyBrowser(alert) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification("SOS AKTIF", {
    body: `${alert.hiker_code || "?"} — ${alertLabel(alert.alert_type)}`,
    requireInteraction: true,
    tag: `sos-${alert.id}`, // tag sama + renotify: pengulangan tetap berbunyi/muncul lagi, bukan diam-diam menimpa
    renotify: true,
  });
}

// Alarm SOS yang belum ditangani diulang tiap 5 menit (bunyi + notifikasi browser) sampai di-dismiss/ditandai
// ditangani, atau sampai SOS dibatalkan dari alat (kartu hilang). Begitu daftar kosong, pengulangan berhenti.
const REPEAT_MS = 5 * 60 * 1000;
let repeatTimer = null;
function stopRepeat() {
  if (repeatTimer) clearInterval(repeatTimer);
  repeatTimer = null;
}
function repeatAlarm() {
  const pending = sosAlerts.value;
  if (!pending.length) {
    stopRepeat();
    return;
  }
  beep();
  pending.forEach(notifyBrowser);
}
function startRepeat() {
  stopRepeat();
  repeatTimer = setInterval(repeatAlarm, REPEAT_MS);
}

// Trigger beep + notifikasi HANYA buat alert yang BENERAN baru terjadi (ditandai _live oleh alertStore:
// datang lewat SSE, atau baru ketahuan lewat sinkronisasi berkala setelah muat awal).
// Alarm yang sudah ACTIVE di database saat dashboard dibuka (muat awal) tetap TAMPIL sebagai kartu supaya
// operator tidak melewatkan SOS yang belum ditangani, tapi tidak membunyikan alarm / notifikasi browser.
// Sebelumnya knownIds kosong saat muat awal, sehingga semua alarm lama dianggap "baru" -> bunyi + notifikasi.
watch(
  sosAlerts,
  (alerts) => {
    let fresh = false;
    for (const a of alerts) {
      if (!knownIds.has(a.id) && a._live) {
        beep();
        notifyBrowser(a);
        fresh = true;
      }
    }
    knownIds = new Set(alerts.map((a) => a.id));
    // ada alarm belum ditangani -> jaga timer 5 menit (diulang dari nol saat ada SOS baru); kosong -> hentikan
    if (!alerts.length) stopRepeat();
    else if (fresh || !repeatTimer) startRepeat();
  },
  { deep: true, immediate: true }
);

// Jaring pengaman: siaran SSE tidak diulang bila koneksi sempat putus (backend restart, laptop sleep, dsb.),
// sehingga SOS yang terjadi saat itu tidak pernah muncul sampai halaman di-refresh. Sinkronkan daftar alarm
// dari server tiap 10 detik; alarm yang baru ketahuan di sini ditandai _live dan dibunyikan.
let syncTimer = null;
onMounted(() => {
  syncTimer = setInterval(() => alertStore.sync(), 10000);
});
onBeforeUnmount(() => {
  clearInterval(syncTimer);
  stopRepeat();
});

// SOS dibatalkan dari alat (payload posisi terbaru sos=false) -> kartu SOS di dashboard otomatis hilang.
watch(
  [() => hikerStore.hikers, () => alertStore.alerts.length],
  () => alertStore.cancelBySosFlag(hikerStore.hikers),
  { deep: true }
);

// ── alarm "node tidak terdengar" & "baterai rendah" (turunan dari data yang sudah ada) ──
const muted = reactive({}); // kode alat -> true = disenyapkan sampai terdengar lagi
const LOW_BATT_PCT = 20; // sama dengan batas merah indikator baterai di panel pemantauan

const silentNodes = computed(() => diagStore.list.filter((d) => d.stale && !muted[d.hiker_code]));
const lowBattery = computed(() =>
  Object.entries(hikerStore.hikers)
    .filter(([, h]) => h.battery_pct != null && h.battery_pct < LOW_BATT_PCT)
    .map(([code, h]) => ({ code, pct: h.battery_pct }))
);
const alarmActive = computed(() => alertStore.alerts.length + silentNodes.value.length + lowBattery.value.length > 0);

function muteSilent(code) {
  muted[code] = true;
}
function fmtAge(s) {
  if (s == null) return "—";
  return s >= 3600 ? `${Math.floor(s / 3600)} jam` : s >= 60 ? `${Math.floor(s / 60)} menit` : `${Math.round(s)} detik`;
}

// bunyi sekali saat node BARU menjadi tidak terdengar / baterai BARU turun di bawah batas
let knownSilent = new Set();
watch(
  () => diagStore.list.map((d) => `${d.hiker_code}:${d.stale}`).join("|"),
  () => {
    const now = new Set(diagStore.list.filter((d) => d.stale).map((d) => d.hiker_code));
    for (const c of Object.keys(muted)) if (!now.has(c)) delete muted[c]; // terdengar lagi -> alarm bisa muncul lagi nanti
    if ([...now].some((c) => !knownSilent.has(c) && !muted[c])) play("silent");
    knownSilent = now;
  }
);
let knownLow = new Set();
watch(
  () => lowBattery.value.map((b) => b.code).join("|"),
  () => {
    const now = new Set(lowBattery.value.map((b) => b.code));
    if ([...now].some((c) => !knownLow.has(c))) play("battery");
    knownLow = now;
  }
);

function acknowledgeAll() {
  // Hanya alarm SOS yang bisa di-"tandai ditangani". OFF_TRAIL tidak pernah disenyapkan manual.
  [...sosAlerts.value].forEach((a) => alertStore.acknowledge(a.id));
}
</script>

<style scoped>
/* tumpukan alarm: pojok kiri-atas area peta. Kartu berbentuk BARIS (ikon | teks | tombol) agar hemat tempat */
.sos-stack {
  position: fixed;
  top: calc(var(--top) + 12px);
  left: calc(var(--lw) + 3 * var(--edge));
  z-index: 5000;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  pointer-events: none;
  max-width: calc(100vw - var(--lw) - var(--rw) - 6 * var(--edge));
}
.sos-list { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; max-width: 100%; }

.sos-pill {
  pointer-events: none; display: inline-flex; align-items: center; gap: 8px; background: var(--red); color: #fff;
  border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 700; box-shadow: var(--shadow-pop);
}
.sos-pill svg { width: 18px; height: 18px; fill: none; stroke: #fff; stroke-width: 2.2; stroke-linecap: round; }

.sos-ack-all {
  pointer-events: auto; background: var(--panel-2); border: 1px solid var(--line-3); color: var(--text);
  border-radius: 8px; padding: 5px 12px; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.sos-ack-all:hover { background: var(--panel-3); }
.sos-sound {
  pointer-events: auto; background: var(--btn-alt); border: 1px solid var(--btn-alt); color: var(--on-btn-alt); border-radius: 8px;
  padding: 6px 12px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit;
}
.sos-sound:hover { background: var(--btn-alt-hover); border-color: var(--btn-alt-hover); }

/* kartu alarm (baris): bingkai merah untuk SOS; peringatan non-SOS memakai garis netral tipis tanpa bingkai warna */
.sos-card {
  pointer-events: auto; display: flex; align-items: center; flex-wrap: nowrap; gap: 10px;
  background: var(--panel-2); color: var(--text); border: 2px solid var(--red); border-radius: 10px;
  padding: 7px 10px; box-shadow: var(--shadow-pop); width: max-content; min-width: 300px; max-width: min(580px, 100%);
  animation: sos-pulse 1.6s ease-in-out infinite;
}
.sos-card.warn { border-width: 1px; border-color: var(--line-3); animation: none; }
.sos-icon {
  font-size: 11px; font-weight: 800; flex-shrink: 0; background: var(--red); color: #fff;
  border-radius: 999px; padding: 5px 8px; line-height: 1;
}
/* Kartu "tidak terdengar"/"baterai rendah" = peringatan, ikon oranye-amber (bukan oranye-trail --accent,
   dan bukan merah SOS). SOS asli di kartu non-.warn tetap merah. */
.sos-card.warn .sos-icon { background: var(--amber); color: var(--on-amber); border-radius: 6px; }
.sos-text { display: flex; flex-direction: column; font-size: 12px; line-height: 1.35; flex: 1; min-width: 0; color: var(--text-2); }
.sos-text strong { font-size: 13px; color: var(--text); }
.sos-text span { text-transform: none; }
.sos-ack {
  background: var(--red); border: 1px solid var(--red); color: #fff; border-radius: 6px; padding: 5px 10px;
  font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; flex-shrink: 0; font-family: inherit;
}
.sos-ack:hover { filter: brightness(0.92); }
.sos-card.warn .sos-ack { background: transparent; color: var(--text); border-color: var(--line-3); }
.sos-card.warn .sos-ack:hover { background: var(--panel-3); color: var(--text); filter: none; }
@keyframes sos-pulse {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  50% { box-shadow: 0 0 0 5px var(--red-pulse); }
}
.drop-enter-active, .drop-leave-active { transition: all 0.25s ease; }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-16px); }
.drop-move { transition: transform 0.25s ease; }
@media (max-width: 1100px) {
  .sos-stack { left: 8px; top: 140px; max-width: 96vw; }
}
</style>