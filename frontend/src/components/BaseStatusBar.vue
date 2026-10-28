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

    <!-- baterai relay (dari CSV_RELAY_BATTERY); tombol baru muncul setelah ada laporan -->
    <button
      v-if="relays.items.length"
      class="bb-btn" :class="{ low: relayAlert }" type="button"
      :aria-expanded="openRelay" aria-haspopup="dialog" :title="relayAlert ? 'Ada relay dengan baterai rendah, sensor bermasalah, atau tidak terdengar.' : 'Status baterai relay'"
      @click="toggleRelays"
    >{{ relayAlert ? "! " : "" }}Relay ({{ relays.items.length }}){{ relayMin != null ? ` · terendah ${relayMin}%` : "" }}</button>

    <span class="bb-sep" aria-hidden="true"></span>

    <!-- suara alarm: browser memblokir bunyi sampai ada klik -->
    <button
      v-if="!sound.enabled" class="bb-btn warn" type="button"
      title="Browser memblokir suara sampai Anda menekan tombol ini. Tanpa ini alarm SOS hanya tampil visual."
      @click="enableSound"
    ><svg class="bb-spk" viewBox="0 0 24 24"><path d="M11 5 6 9H3v6h3l5 4zM16 9a4 4 0 0 1 0 6" /></svg>Aktifkan suara alarm</button>
    <button v-else class="bb-btn ok" type="button" title="Suara alarm aktif. Klik untuk mencoba bunyinya." @click="enableSound">
      <svg class="bb-spk" viewBox="0 0 24 24"><path d="M11 5 6 9H3v6h3l5 4zM16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12" /></svg>Alarm aktif
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

    <!-- baterai relay -->
    <div v-if="openRelay" class="bb-pop" role="dialog" aria-label="Baterai relay" @keydown.esc="openRelay = false">
      <div class="bb-pop-h">
        <strong>Baterai relay</strong>
        <button class="bb-x" type="button" aria-label="Tutup" @click="openRelay = false">✕</button>
      </div>
      <p class="bb-hint">Dilaporkan tiap relay sekitar 30 detik sekali lewat base. Persen adalah perkiraan dari tegangan, bukan pengukur kapasitas yang akurat.</p>
      <div v-for="r in relayRows" :key="r.relay_id" class="bb-opt" :class="{ cur: r.problem }">
        <span>
          <b>{{ r.title }}</b>
          <span class="bb-tag" :class="{ bad: r.problem }">{{ r.status }}</span>
          <br />
          <small>{{ r.detail }}</small>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useBaseStore } from "../stores/base";
import { RELAY_LOW_PCT, RELAY_STALE_MS, useRelayStore } from "../stores/relays";
import { useDiagnosticsStore } from "../stores/diagnostics";
import { enableSound, sound } from "../composables/useAlarmSound";

const store = useBaseStore();
const diag = useDiagnosticsStore();
const open = ref(false);
const relays = useRelayStore();
const openRelay = ref(false);
onMounted(() => relays.start());
onUnmounted(() => relays.stop());

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
  if (open.value) openRelay.value = false;
  if (open.value) await store.loadPorts();
}
function toggleRelays() {
  openRelay.value = !openRelay.value;
  if (openRelay.value) open.value = false;
}

// Teks status sensor baterai relay (gauge_state dari firmware)
const GAUGE_TEXT = {
  NO_DEVICE: "sensor baterai tidak terdeteksi",
  IO_ERROR: "sensor baterai error",
  INVALID: "pembacaan sensor tidak valid",
  STALE: "pembacaan sensor basi",
  WARMING_UP: "sensor sedang menghangat",
  UNKNOWN: "status sensor tidak diketahui",
};
const relayRows = computed(() =>
  relays.items.map((r) => {
    // umur laporan = umur saat diambil dari server + waktu yang berlalu sejak itu (tidak bergantung jam laptop)
    const ageMs = r.age_s * 1000 + (store.now - relays.fetchedAt);
    const silent = r.stale || ageMs > RELAY_STALE_MS;
    const ok = r.gauge_state === "OK" && r.battery_pct != null;
    const low = ok && r.battery_pct <= RELAY_LOW_PCT;
    let status = "normal";
    if (silent) status = "tidak terdengar";
    else if (!ok) status = "sensor bermasalah";
    else if (low) status = "baterai rendah";
    const bits = [];
    if (ok) bits.push(`${r.battery_pct}% · ${Number(r.volts).toFixed(2)} V`);
    else bits.push(GAUGE_TEXT[r.gauge_state] || GAUGE_TEXT.UNKNOWN);
    bits.push(`laporan ${ago(ageMs)}`);
    if (r.rssi_dbm != null) bits.push(`RSSI ${r.rssi_dbm} dBm`);
    if (r.route_path && r.route_path !== "LANGSUNG") bits.push(`via ${r.route_path}`);
    return {
      relay_id: r.relay_id,
      title: r.name ? `${r.name} (R${r.relay_id})` : `Relay R${r.relay_id}`,
      status, problem: status !== "normal", detail: bits.join(" · "),
      pct: ok && !silent ? r.battery_pct : null,
    };
  })
);
const relayAlert = computed(() => relayRows.value.some((r) => r.problem));
const relayMin = computed(() => {
  const v = relayRows.value.map((r) => r.pct).filter((x) => x != null);
  return v.length ? Math.min(...v) : null;
});
async function choose(port) {
  await store.choosePort(port);
}
</script>

<style scoped>
/* bilah status: menempel di pojok kiri-bawah peta */
.base-bar {
  bottom: var(--edge); left: calc(var(--lw) + 2 * var(--edge)); right: auto; margin: 0; width: fit-content; max-width: calc(100vw - var(--lw) - var(--rw) - 4 * var(--edge)); z-index: 30;
  display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-start; gap: 4px 8px;
  padding: 4px 8px; border-radius: 0 var(--rs) 0 var(--radius); font-size: 12px; border-color: var(--line); border-left: 0; border-bottom: 0;
  background: var(--panel-2);
}
.bb-status { display: inline-flex; align-items: center; gap: 6px; padding: 2px 4px; font-weight: 700; border: 1px solid transparent; border-radius: 6px; }
.bb-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
.bb-status.ok { color: var(--green); }
.bb-status.ok .bb-dot { background: var(--green); }
.bb-status.warn { color: var(--text); }
.bb-status.warn .bb-dot { background: var(--amber); }
/* Kegagalan koneksi base (terputus/USB/tak terjangkau) = PERINGATAN operasional, bukan SOS.
   Pakai amber, bukan merah (merah = SOS saja). Tetap menonjol dengan latar penuh + ikon. */
.bb-status.bad { background: var(--amber); color: var(--on-amber); padding: 2px 8px; }
.bb-status.bad .bb-dot { background: var(--on-amber); }
.bb-status.off { color: var(--text-2); }
.bb-icon { display: none; }
.bb-port { font-weight: 600; opacity: 0.9; font-size: 11px; }
.bb-last { color: var(--text-2); font-size: 11px; line-height: 1.2; white-space: nowrap; }
.bb-sep { display: none; }
.bb-btn {
  min-height: 26px; padding: 2px 9px; border-radius: 6px; border: 1px solid var(--blue-fg); background: transparent;
  color: var(--blue-fg); font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 5px;
}
.bb-spk { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.bb-btn:hover:not(:disabled) { background: var(--blue-glow); }
.bb-btn:disabled { opacity: 0.5; cursor: wait; }
.bb-btn.attn { background: var(--accent-glow); border-color: var(--accent); }
.bb-btn.warn { border-color: var(--btn-alt); background: var(--btn-alt); color: var(--on-btn-alt); }
.bb-btn.warn:hover:not(:disabled) { background: var(--btn-alt-hover); border-color: var(--btn-alt-hover); }
.bb-btn.low { background: var(--amber); border-color: var(--amber); color: var(--on-amber); }
.bb-btn.low:hover:not(:disabled) { filter: brightness(1.08); background: var(--amber); }
.bb-tag.bad { background: var(--amber); border-color: var(--amber); color: var(--on-amber); }
.bb-btn.ok { color: var(--green); border-color: var(--green); }
.bb-btn.ok:hover:not(:disabled) { background: var(--green-bg); }
.bb-pop {
  position: absolute; bottom: calc(100% + 6px); left: 0; width: min(92vw, 360px);
  max-height: min(60vh, 340px); overflow-y: auto; z-index: 31;
  background: var(--panel-2); border: 1px solid var(--line-3); border-radius: var(--rs); padding: 10px; display: flex; flex-direction: column; gap: 7px;
  box-shadow: var(--shadow-pop); text-align: left;
}
.bb-pop-h { display: flex; justify-content: space-between; align-items: center; font-size: 13px; position: sticky; top: 0; background: var(--panel-2); }
.bb-x { background: none; border: none; color: var(--text-2); font-size: 16px; cursor: pointer; padding: 2px 6px; }
.bb-hint { font-size: 12px; color: var(--text-2); line-height: 1.4; }
.bb-opt { display: flex; align-items: flex-start; gap: 8px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 7px; cursor: pointer; font-size: 12px; line-height: 1.35; }
.bb-opt.cur { border-color: var(--blue-fg); background: var(--blue-glow); }
.bb-opt small { color: var(--text-2); font-size: 11px; }
.bb-tag { margin-left: 6px; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 6px; border: 1px solid var(--line-3); color: var(--text-2); }
.bb-tag.on { color: var(--green); border-color: var(--green); }
.bb-empty { font-size: 12px; color: var(--text-2); padding: 6px 2px; }
.bb-err { font-size: 12px; color: var(--text); background: var(--amber-glow); border: 1px solid var(--amber); border-radius: 8px; padding: 7px 9px; }
@media (max-width: 1100px) { .base-bar { position: fixed; left: 8px; right: 8px; bottom: 8px; border: 1px solid var(--line); border-radius: var(--rs); max-width: none; } }
</style>