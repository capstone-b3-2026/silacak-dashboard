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

      <!--
        Kartu di bawah ini (signal trend, latency timeline, RF params)
        masih placeholder murni - backend belum punya tabel/endpoint buat
        telemetry per-link (SNR, margin, PDR, latency, cuaca, SF/ToA).
        Struktur & class-nya udah final, tinggal isi datanya nanti.
      -->
      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M2 12h4l3-8 4 16 3-8h6" /></svg>Tren sinyal</div><div class="sv">Menunggu data</div></div>
        <div class="pb">
          <div class="sgrid">
            <div class="sc" v-for="t in trends" :key="t">
              <div class="sc-h"><strong>{{ t }}</strong><span>—</span></div>
              <div class="sc-w">
                <svg viewBox="0 0 100 24" preserveAspectRatio="none"><line x1="0" y1="12" x2="100" y2="12" /></svg>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>Tunda data (latency)</div><div class="sv">{{ latText }}</div></div>
        <div class="pb" style="padding-bottom: 8px">
          <div class="ekg-c">
            <div class="ekg-h"><strong>Grafik berjalan</strong><span>—</span></div>
            <div class="ekg-w">Belum ada data telemetri link yang masuk</div>
          </div>
        </div>
      </div>

      <div v-if="uiStore.advanced" class="pnl">
        <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0" /><circle cx="12" cy="12" r="1" /></svg>Parameter radio</div><div class="sv">—</div></div>
        <div class="pb">
          <div class="rf-row">
            <div class="rf-c"><strong>Kondisi cuaca</strong><span>—</span></div>
            <div class="rf-c"><strong>SF / waktu udara</strong><span>—</span></div>
          </div>
          <div class="lgnd">
            <div class="lg"><span class="sw circle" style="background: var(--marker)"></span>Pendaki</div>
            <div class="lg"><span class="sw circle" style="background: var(--red)"></span>SOS</div>
            <div class="lg dim"><span class="sw circle" style="background: var(--accent)"></span>Relay (belum ada data)</div>
            <div class="lg dim"><span class="sw circle" style="background: var(--green)"></span>Base (belum ada data)</div>
            <div class="lg dim"><span class="sw line" style="background: var(--green)"></span>Link kuat (belum ada data)</div>
            <div class="lg dim"><span class="sw line" style="background: var(--amber)"></span>Link marginal (belum ada data)</div>
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
import { useUiStore } from "../stores/ui";
import StartGuide from "./StartGuide.vue";
import DataPanel from "./DataPanel.vue";

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
const trends = ["Paket sampai", "Tunda data", "SNR", "Margin"];
</script>