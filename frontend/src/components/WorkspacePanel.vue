<template>
  <aside class="floating sidebar left" :class="{ collapsed }">
    <div class="sh">
      <button class="tbtn" @click="collapsed = !collapsed" :aria-expanded="!collapsed" title="Ciutkan atau buka panel" aria-label="Ciutkan atau buka panel kiri">
        <svg viewBox="0 0 24 24"><path d="M14 5l-7 7 7 7" /></svg>
      </button>
      <div class="slbl ch">
        <strong>Ruang kerja</strong>
        <span>{{ uiStore.advanced ? "Mode lanjutan" : "Mode harian" }}</span>
      </div>
      <button
        class="tbtn ch" :class="{ on: showGuide }" type="button"
        :aria-expanded="showGuide" aria-haspopup="dialog"
        title="Panduan langkah memulai" aria-label="Buka panduan langkah memulai"
        @click="showGuide = !showGuide"
      >
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M9.6 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.2.9-1.2 1.8" /><line x1="12" y1="17" x2="12" y2="17.01" /></svg>
      </button>
      <span class="ch" style="display: flex; align-items: center; font-size: 12px; color: var(--text-2); white-space: nowrap">
        <span class="conn-dot" :class="{ live: pendakiAktif > 0 }"></span>
        <span>{{ pendakiAktif > 0 ? "Data masuk" : "Menunggu data" }}</span>
      </span>
    </div>

    <!-- panduan: dibuka dari tombol bantuan di header, tidak lagi memenuhi sidebar -->
    <StartGuide class="ch" :open="showGuide" @close="showGuide = false" />

    <div class="sb ch">
      <SessionsPanel />

      <!-- ringkasan -->
      <div class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M3 3v18h18" /><path d="M7 15l4-5 3 3 5-7" /></svg>Ringkasan</div><div class="sv">{{ pendakiAktif > 0 ? "Data masuk" : "Menunggu data" }}</div></div>
        <div class="pb">
          <div class="mgrid">
            <div class="mc"><span class="mc-ic"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg></span><div class="mc-t"><strong>{{ pendakiAktif }}</strong><span class="mc-l">Pendaki aktif</span></div></div>
            <div class="mc" :class="{ alert: sosAktif > 0 }"><span class="mc-ic sos">SOS</span><div class="mc-t"><strong>{{ sosAktif }}</strong><span class="mc-l">SOS aktif</span></div></div>
            <template v-if="uiStore.advanced">
              <div class="mc" :class="{ good: pdr != null && pdr >= 90, alert: pdr != null && pdr < 80 }" :title="`PDR = persentase paket yang sampai ke base. Ambang rencana: jalur lurus ≥90%, terhalang ≥80% · ${diagStore.list.length} sesi`"><span class="mc-ic ok"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.7 2.7L16 9.5" /></svg></span><div class="mc-t"><strong :style="pdr == null ? 'color: var(--muted)' : ''">{{ pdr == null ? "—" : `${pdr.toFixed(0)}%` }}</strong><span class="mc-l">Paket yang sampai</span></div></div>
              <div class="mc" :title="latTitle"><span class="mc-ic"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg></span><div class="mc-t"><strong :style="lat == null ? 'color: var(--muted)' : ''">{{ latText }}</strong><span class="mc-l">Tunda data (latency)</span></div></div>
            </template>
          </div>
        </div>
      </div>

      <!-- Tren sinyal: RSSI & tunda data diambil dari log paket pendaki terpilih (diagStore.trend, diperbarui tiap 5 dtk) -->
      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M2 12h4l3-8 4 16 3-8h6" /></svg>Tren sinyal</div><div class="sv">{{ trendLabel }}</div></div>
        <div class="pb">
          <div class="sgrid">
            <div class="sc" v-for="c in trendCards" :key="c.key">
              <div class="sc-h"><strong :title="c.title">{{ c.label }}</strong><span :style="c.value === '—' ? 'color: var(--muted)' : ''">{{ c.value }}</span></div>
              <div class="sc-w">
                <Sparkline :vals="c.vals" :line-class="c.cls" :format="c.format" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>Tunda data (latency)</div><div class="sv">{{ latText }}</div></div>
        <div class="pb" style="padding-bottom: 8px">
          <div class="ekg-c">
            <div class="ekg-h"><strong :title="latTitle">Grafik berjalan</strong><span>{{ latRangeText }}</span></div>
            <div v-if="latVals.length" class="ekg-svg"><Sparkline :vals="latVals" :w="300" :h="56" :pad="4" line-class="lat" :format="fmtLat" /></div>
            <div v-else class="ekg-w">{{ latEmptyText }}</div>
          </div>
        </div>
      </div>


      <DataPanel v-if="uiStore.advanced" />

    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";
import { useHikerStore } from "../stores/hikers";
import { useAlertStore } from "../stores/alerts";
import SessionsPanel from "./SessionsPanel.vue";
import { useDiagnosticsStore } from "../stores/diagnostics";
import { useUiStore } from "../stores/ui";
import StartGuide from "./StartGuide.vue";
import DataPanel from "./DataPanel.vue";
import Sparkline from "./Sparkline.vue";

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const collapsed = ref(false);
const showGuide = ref(false);
const diagStore = useDiagnosticsStore();
const uiStore = useUiStore();
const pdr = computed(() => diagStore.pdrOverall);
const lat = computed(() => diagStore.latencyMedianS);
// median latency antar sesi (detik). Negatif = jam laptop tidak sinkron dengan jam GPS node.
const latText = computed(() => (lat.value == null ? "—" : lat.value < 0 ? "jam?" : `${lat.value.toFixed(1)} s`));
const latTitle = computed(() => lat.value != null && lat.value < 0
  ? "Negatif: jam laptop tidak sinkron dengan waktu GPS alat. Sinkronkan jam laptop (NTP)."
  : "Tunda data: selisih waktu paket diterima dengan waktu GPS alat (median). Ambang rencana: ≤15 dtk (lewat 1 relay), ≤30 dtk (2 relay).");

const pendakiAktif = computed(() => Object.keys(hikerStore.hikers).length);
const sosAktif = computed(() => alertStore.alerts.length);

// ── Tren sinyal & tunda data ──
// Sumber: log paket pendaki terpilih (GET /diagnostics/{kode}/packets, terbaru dulu) yang sudah di-poll diagStore.
// Dulu kartu ini hanya placeholder statis ("—" + garis datar) dan tidak terhubung ke store mana pun.
const WINDOW = 60; // jumlah paket terakhir yang digambar
const series = computed(() => diagStore.trend.slice(0, WINDOW).reverse()); // urut waktu lama -> baru
const rssiVals = computed(() => series.value.map((p) => p.rssi_dbm).filter((v) => v != null));
const latVals = computed(() => series.value.map((p) => p.latency_s).filter((v) => v != null));
const last = (arr) => (arr.length ? arr[arr.length - 1] : null);

// Penggambaran garis/skala + crosshair hover kini di Sparkline.vue. Di sini cukup siapkan data & formatter nilai.
const fmtLat = (v) => (v == null ? "—" : v < 0 ? "jam?" : `${v.toFixed(1)} s`);

const trendLabel = computed(() => (diagStore.trendFor ? `${diagStore.trendFor} · ${series.value.length} paket` : "Menunggu data"));
const trendCards = computed(() => [
  {
    key: "rssi", label: "Kekuatan sinyal", cls: "rssi",
    value: last(rssiVals.value) != null ? `${last(rssiVals.value)} dBm` : "—",
    vals: rssiVals.value,
    format: (v) => `${v} dBm`,
    title: "RSSI paket yang diterima base (dBm). Makin mendekati 0 makin kuat; di bawah sekitar −110 dBm hampir putus.",
  },
  {
    key: "lat", label: "Tunda data", cls: "lat",
    value: fmtLat(last(latVals.value)),
    vals: latVals.value,
    format: fmtLat,
    title: "Selisih waktu paket diterima dengan waktu GPS alat, per paket.",
  },
  // Kartu PDR ("Paket sampai") dihapus dari sini: nilainya identik dengan kartu PDR di
  // section Ringkasan (sama-sama diagStore.pdrOverall) dan PDR bukan deret rolling, jadi
  // sparkline selalu kosong (garis datar). Angka PDR tetap tampil di Ringkasan.
]);

const latRangeText = computed(() => {
  if (!latVals.value.length) return "—";
  const lo = Math.min(...latVals.value), hi = Math.max(...latVals.value);
  return `${lo.toFixed(1)}–${hi.toFixed(1)} s · ${latVals.value.length} paket`;
});
const latEmptyText = computed(() =>
  diagStore.trend.length
    ? "Paket sudah masuk, tetapi belum ada yang membawa waktu GPS valid (tanggal & jam di alat belum tersinkron), jadi tunda data belum bisa dihitung"
    : "Belum ada data telemetri link yang masuk"
);

// Legenda peta dipindah dari panel ini ke popover di MapView.vue.
</script>

<style scoped>
/* Garis/warna sparkline + crosshair kini di Sparkline.vue. Di sini cukup wadah grafik besar. */
.ekg-svg { width: 100%; height: 56px; display: block; }
/* grafik besar: wrapper Sparkline (child) harus mengisi tinggi 56px wadah ini */
.ekg-svg :deep(.spark) { height: 100%; }
</style>