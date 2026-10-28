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

      <DataPanel v-if="uiStore.advanced" />

      <!-- Tren sinyal: RSSI & tunda data diambil dari log paket pendaki terpilih (diagStore.trend, diperbarui tiap 5 dtk) -->
      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M2 12h4l3-8 4 16 3-8h6" /></svg>Tren sinyal</div><div class="sv">{{ trendLabel }}</div></div>
        <div class="pb">
          <div class="sgrid">
            <div class="sc" v-for="c in trendCards" :key="c.key" :title="c.title">
              <div class="sc-h"><strong>{{ c.label }}</strong><span :style="c.value === '—' ? 'color: var(--muted)' : ''">{{ c.value }}</span></div>
              <div class="sc-w">
                <svg viewBox="0 0 100 24" preserveAspectRatio="none">
                  <polyline v-if="c.points" :points="c.points" class="sp" :class="c.cls" />
                  <line v-else x1="0" y1="12" x2="100" y2="12" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>Tunda data (latency)</div><div class="sv">{{ latText }}</div></div>
        <div class="pb" style="padding-bottom: 8px">
          <div class="ekg-c">
            <div class="ekg-h"><strong>Grafik berjalan</strong><span>{{ latRangeText }}</span></div>
            <svg v-if="latGraph" class="ekg-svg" viewBox="0 0 300 56" preserveAspectRatio="none"><polyline :points="latGraph" class="sp lat" /></svg>
            <div v-else class="ekg-w">{{ latEmptyText }}</div>
          </div>
        </div>
      </div>

      <!-- legenda peta (dulu satu kartu dengan "Parameter radio"; kartu parameter radio sudah dihapus) -->
      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>Legenda peta</div></div>
        <div class="pb">
          <div class="lgnd">
            <div class="lg"><span class="sw circle" style="background: var(--marker)"></span>Pendaki</div>
            <div class="lg"><span class="sw circle" style="background: var(--red)"></span>SOS</div>
            <div class="lg" :class="{ dim: !relayActive }"><span class="sw circle" style="background: var(--violet)"></span>Relay{{ lgSuffix(relayActive) }}</div>
            <div class="lg" :class="{ dim: !baseActive }"><span class="sw circle" style="background: var(--green)"></span>Base{{ lgSuffix(baseActive) }}</div>
            <div class="lg" :class="{ dim: !linkKuatActive }"><span class="sw line" style="background: var(--green)"></span>Link kuat{{ lgSuffix(linkKuatActive) }}</div>
            <div class="lg" :class="{ dim: !linkMarginalActive }"><span class="sw line" style="background: var(--amber)"></span>Link marginal{{ lgSuffix(linkMarginalActive) }}</div>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";
import { useHikerStore } from "../stores/hikers";
import { useAlertStore } from "../stores/alerts";
import SessionsPanel from "./SessionsPanel.vue";
import { useDiagnosticsStore } from "../stores/diagnostics";
import { useSiteStore } from "../stores/site";
import { useUiStore } from "../stores/ui";
import StartGuide from "./StartGuide.vue";
import DataPanel from "./DataPanel.vue";

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const collapsed = ref(false);
const showGuide = ref(false);
const diagStore = useDiagnosticsStore();
const siteStore = useSiteStore();
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

// titik polyline dalam kotak W x H; tinggi diskalakan min..max data (data datar -> garis tengah)
function spark(vals, W = 100, H = 24, pad = 2) {
  if (!vals.length) return "";
  if (vals.length === 1) return `0,${H / 2} ${W},${H / 2}`;
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const n = vals.length;
  return vals
    .map((v, i) => `${((i / (n - 1)) * W).toFixed(1)},${(H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad)).toFixed(1)}`)
    .join(" ");
}
const fmtLat = (v) => (v == null ? "—" : v < 0 ? "jam?" : `${v.toFixed(1)} s`);

const trendLabel = computed(() => (diagStore.trendFor ? `${diagStore.trendFor} · ${series.value.length} paket` : "Menunggu data"));
const trendCards = computed(() => [
  {
    key: "rssi", label: "Kekuatan sinyal", cls: "rssi",
    value: last(rssiVals.value) != null ? `${last(rssiVals.value)} dBm` : "—",
    points: spark(rssiVals.value),
    title: "RSSI paket yang diterima base (dBm). Makin mendekati 0 makin kuat; di bawah sekitar −110 dBm hampir putus.",
  },
  {
    key: "lat", label: "Tunda data", cls: "lat",
    value: fmtLat(last(latVals.value)),
    points: spark(latVals.value),
    title: "Selisih waktu paket diterima dengan waktu GPS alat, per paket.",
  },
  // Kartu PDR ("Paket sampai") dihapus dari sini: nilainya identik dengan kartu PDR di
  // section Ringkasan (sama-sama diagStore.pdrOverall) dan PDR bukan deret rolling, jadi
  // sparkline selalu kosong (garis datar). Angka PDR tetap tampil di Ringkasan.
]);

const latGraph = computed(() => spark(latVals.value, 300, 56, 4));
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

// ── Keadaan legenda peta ──
// Suffix "(belum ada data)" dan class "dim" hanya muncul saat elemen itu BELUM ada di peta.
// Sumbernya rencana lokasi (siteStore) — sama dengan yang digambar MapView.siteGeo, bukan telemetri paket.
const baseActive = computed(() => !!siteStore.site?.base || diagStore.baseSet);
const planRelays = computed(() => siteStore.site?.plan?.relays || []);
const relayActive = computed(() => planRelays.value.length > 0);
// Garis link hanya tergambar bila base ter-set DAN ada minimal satu relay (MapView.siteGeo: st?.base && relays.length).
const linksDrawn = computed(() => baseActive.value && relayActive.value);
// Klasifikasi kuat vs marginal mengikuti logika MapView.siteGeo: fade_margin_db < ambang params => marginal.
const fadeThreshold = computed(() => siteStore.site?.params?.fade_margin_db ?? 10);
const isMarginal = (r) => {
  if (r.link_ok === false) return false; // link tak-layak dirender merah, bukan marginal
  if (r.fade_margin_db != null) return r.fade_margin_db < fadeThreshold.value;
  const loss = r.loss_db ?? (r.margin_m < 3 ? 6 : 0); // rencana lama hanya punya margin
  return loss > 3;
};
const linkKuatActive = computed(() => linksDrawn.value && planRelays.value.some((r) => r.link_ok !== false && !isMarginal(r)));
const linkMarginalActive = computed(() => linksDrawn.value && planRelays.value.some((r) => isMarginal(r)));

// Legenda: label normal saat aktif, "(belum ada data)" + dim saat belum ada.
const lgSuffix = (active) => (active ? "" : " (belum ada data)");
</script>

<style scoped>
.sp { fill: none; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.sp.rssi { stroke: var(--blue-fg); }
.sp.lat { stroke: var(--accent); }
.ekg-svg { width: 100%; height: 56px; display: block; }
</style>