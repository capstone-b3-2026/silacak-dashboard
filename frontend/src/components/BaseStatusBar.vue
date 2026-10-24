<template>
  <div class="base-bar floating" role="region" aria-label="Status base station dan suara alarm">
    <!-- status base: warna + ikon + teks (tidak mengandalkan warna saja) -->
    <div class="bb-status" :class="view.tone" role="status" aria-live="polite" :title="view.hint">
      <span class="bb-dot" aria-hidden="true"></span>
      <span class="bb-icon" aria-hidden="true">{{ view.icon }}</span>
      <span class="bb-label">{{ view.label }}</span>
      <span v-if="view.port" class="bb-port">{{ view.port }}</span>
    </div>

    <div class="bb-last" :title="'Waktu paket terakhir dari alat pendaki diterima base'">{{ lastText }}</div>

    <button
      v-if="canPick"
      class="bb-btn" :class="{ attn: view.attention }" type="button"
      :aria-expanded="open" aria-haspopup="dialog" @click="togglePorts"
    >Pilih port</button>

    <span class="bb-sep" aria-hidden="true"></span>

    <!-- suara alarm: browser memblokir bunyi sampai ada klik -->
    <button
      v-if="!sound.enabled" class="bb-btn warn" type="button"
      title="Browser memblokir suara sampai Anda menekan tombol ini. Tanpa ini alarm SOS hanya tampil visual."
      @click="enableSound"
    ><svg class="bb-spk" viewBox="0 0 24 24"><path d="M11 5 6 9H3v6h3l5 4zM16 9a4 4 0 0 1 0 6" /></svg>Aktifkan suara alarm</button>
    <button v-else class="bb-btn ok" type="button" title="Suara alarm aktif. Klik untuk mencoba bunyinya." @click="enableSound">
      <svg class="bb-spk" viewBox="0 0 24 24"><path d="M11 5 6 9H3v6h3l5 4zM16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12" /></svg>Suara alarm aktif
    </button>

    <!-- pemilih port -->
    <div v-if="open" class="bb-pop" role="dialog" aria-label="Pilih port base station" @keydown.esc="open = false">
      <div class="bb-pop-h">
        <strong>Port base station</strong>
        <button class="bb-x" type="button" aria-label="Tutup" @click="open = false">✕</button>
      </div>
      <p class="bb-hint">Colok base ke USB. Bila hanya satu alat ESP32 terdeteksi, dashboard memilihnya otomatis. Pilih manual kalau ada banyak port.</p>

      <label class="bb-opt" :class="{ cur: store.status?.requested === 'auto' }">
        <input type="radio" name="bport" :checked="store.status?.requested === 'auto'" @change="choose('auto')" />
        <span><b>Otomatis</b> <small>(disarankan)</small></span>
      </label>
      <label v-for="p in store.ports" :key="p.device" class="bb-opt" :class="{ cur: store.status?.requested === p.device }">
        <input type="radio" name="bport" :checked="store.status?.requested === p.device" @change="choose(p.device)" />
        <span>
          <b>{{ p.device }}</b>
          <small v-if="p.description"> · {{ p.description }}</small>
          <span v-if="p.candidate" class="bb-tag">kemungkinan base</span>
          <span v-if="store.status?.port === p.device" class="bb-tag on">dipakai</span>
        </span>
      </label>
      <div v-if="!store.ports.length && !store.portsLoading" class="bb-empty">Belum ada port serial terdeteksi. Periksa kabel USB lalu segarkan.</div>
      <div v-if="store.error" class="bb-err" role="alert">{{ store.error }}</div>
      <div v-if="store.status?.last_error && view.tone !== 'ok'" class="bb-err">{{ store.status.last_error }}</div>
      <button class="bb-btn" type="button" :disabled="store.portsLoading" @click="store.loadPorts()">
        {{ store.portsLoading ? "Memuat…" : "Segarkan daftar port" }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { useBaseStore } from "../stores/base";
import { useDiagnosticsStore } from "../stores/diagnostics";
import { enableSound, sound } from "../composables/useAlarmSound";

const store = useBaseStore();
const diag = useDiagnosticsStore();
const open = ref(false);

// state backend: off | unavailable | searching | ambiguous | connected | reconnecting
const view = computed(() => {
  const s = store.status;
  if (store.unreachable) return { tone: "bad", icon: "✕", label: "Server tidak terjangkau", hint: "Dashboard tidak bisa menghubungi backend." };
  if (!s) return { tone: "warn", icon: "…", label: "Memeriksa base…", hint: "" };
  const port = s.port || "";
  switch (s.state) {
    case "connected":
      return { tone: "ok", icon: "✓", label: "Base terhubung", port, hint: "Base station terbaca lewat USB." };
    case "searching":
      return { tone: "warn", icon: "…", label: "Mencari base…", hint: "Belum ada alat di port USB. Colok base ke laptop.", attention: true };
    case "ambiguous":
      return { tone: "warn", icon: "!", label: "Beberapa port cocok — pilih port base", hint: "Lebih dari satu port ESP32 terdeteksi; dashboard tidak menebak.", attention: true };
    case "reconnecting":
      return { tone: "bad", icon: "✕", label: "Base terputus", hint: s.last_error || "Kabel USB terlepas atau port tidak bisa dibuka. Mencoba menyambung ulang.", attention: true };
    case "unavailable":
      return { tone: "bad", icon: "✕", label: "Pembaca USB tidak tersedia", hint: s.last_error || "pyserial belum terpasang di backend." };
    case "off":
      return { tone: "off", icon: "–", label: "Base lewat bridge luar", hint: "Pembacaan USB bawaan dimatikan (SERIAL_PORT=off); data masuk lewat bridge eksternal." };
    default:
      return { tone: "warn", icon: "?", label: String(s.state), hint: "" };
  }
});

// POST /base/port ditolak backend (409) kalau ingest serial dimatikan, jadi tombolnya disembunyikan saat "off"/"unavailable"
const canPick = computed(() => !!store.status?.enabled && ["searching", "ambiguous", "connected", "reconnecting"].includes(store.status.state));

// Waktu paket terakhir: dari base kalau ada; kalau mode bridge luar, dari paket terbaru sesi aktif
const lastAt = computed(() => {
  const own = store.status?.last_packet_at;
  if (own) return Date.parse(own);
  let best = null;
  for (const d of diag.list) {
    const t = d.last_heard_at ? Date.parse(d.last_heard_at) : NaN;
    if (!Number.isNaN(t) && (best == null || t > best)) best = t;
  }
  return best;
});
function ago(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} detik lalu`;
  if (s < 3600) return `${Math.floor(s / 60)} menit lalu`;
  if (s < 86400) return `${Math.floor(s / 3600)} jam lalu`;
  return `${Math.floor(s / 86400)} hari lalu`;
}
const lastText = computed(() => (lastAt.value == null ? "Belum ada paket diterima" : `Paket terakhir ${ago(store.now - lastAt.value)}`));

async function togglePorts() {
  open.value = !open.value;
  if (open.value) await store.loadPorts();
}
async function choose(port) {
  await store.choosePort(port);
}
</script>

<style scoped>
/* bilah status: menempel di pojok kiri-bawah peta */
.base-bar {
  bottom: var(--edge); left: calc(var(--lw) + 2 * var(--edge)); right: auto; margin: 0; width: fit-content; max-width: calc(100vw - var(--lw) - var(--rw) - 4 * var(--edge)); z-index: 30;
  display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-start; gap: 8px 14px;
  padding: 8px 14px; border-radius: 0 var(--rs) 0 var(--radius); font-size: 13px; border-color: var(--line); border-left: 0; border-bottom: 0;
  background: var(--panel-2);
}
.bb-status { display: inline-flex; align-items: center; gap: 8px; padding: 4px 4px; font-weight: 700; border: 1px solid transparent; border-radius: 8px; }
.bb-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
.bb-status.ok { color: var(--green); }
.bb-status.ok .bb-dot { background: var(--green); }
.bb-status.warn { color: var(--text); }
.bb-status.warn .bb-dot { background: var(--amber); }
/* Kegagalan koneksi base (terputus/USB/tak terjangkau) = PERINGATAN operasional, bukan SOS.
   Pakai amber, bukan merah (merah = SOS saja). Tetap menonjol dengan latar penuh + ikon. */
.bb-status.bad { background: var(--amber); color: #fff; padding: 4px 12px; }
.bb-status.bad .bb-dot { background: #fff; }
.bb-status.off { color: var(--text-2); }
.bb-icon { display: none; }
.bb-port { font-weight: 600; opacity: 0.9; font-size: 12px; }
.bb-last { color: var(--text-2); font-size: 12px; line-height: 1.25; max-width: 130px; }
.bb-sep { display: none; }
.bb-btn {
  min-height: 34px; padding: 4px 14px; border-radius: 8px; border: 1px solid var(--blue-fg); background: transparent;
  color: var(--blue-fg); font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 6px;
}
.bb-spk { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.bb-btn:hover:not(:disabled) { background: var(--blue-glow); }
.bb-btn:disabled { opacity: 0.5; cursor: wait; }
.bb-btn.attn { background: var(--accent-glow); border-color: var(--accent); }
.bb-btn.warn { border-color: var(--btn); background: var(--btn); color: var(--on-btn); }
.bb-btn.warn:hover:not(:disabled) { background: var(--btn-hover); border-color: var(--btn-hover); }
.bb-btn.ok { color: var(--green); border-color: var(--green); }
.bb-btn.ok:hover:not(:disabled) { background: var(--green-bg); }
.bb-pop {
  position: absolute; bottom: calc(100% + 8px); left: 0; width: min(92vw, 400px);
  background: var(--panel-2); border: 1px solid var(--line-3); border-radius: var(--rs); padding: 14px; display: flex; flex-direction: column; gap: 10px;
  box-shadow: var(--shadow-pop); text-align: left;
}
.bb-pop-h { display: flex; justify-content: space-between; align-items: center; font-size: 15px; }
.bb-x { background: none; border: none; color: var(--text-2); font-size: 18px; cursor: pointer; padding: 2px 8px; }
.bb-hint { font-size: 13px; color: var(--text-2); line-height: 1.5; }
.bb-opt { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; cursor: pointer; font-size: 14px; line-height: 1.4; }
.bb-opt.cur { border-color: var(--blue-fg); background: var(--blue-glow); }
.bb-opt small { color: var(--text-2); font-size: 13px; }
.bb-tag { margin-left: 6px; font-size: 12px; font-weight: 700; padding: 1px 8px; border-radius: 6px; border: 1px solid var(--line-3); color: var(--text-2); }
.bb-tag.on { color: var(--green); border-color: var(--green); }
.bb-empty { font-size: 13px; color: var(--text-2); padding: 6px 2px; }
.bb-err { font-size: 13px; color: var(--text); background: var(--amber-glow); border: 1px solid var(--amber); border-radius: 8px; padding: 8px 10px; }
@media (max-width: 1100px) { .base-bar { position: fixed; left: 8px; right: 8px; bottom: 8px; border: 1px solid var(--line); border-radius: var(--rs); max-width: none; } }
</style>