<template>
  <aside class="floating sidebar left" :class="{ collapsed }">
    <div class="sh">
      <button class="tbtn" @click="collapsed = !collapsed" title="Collapse sidebar">
        <svg viewBox="0 0 24 24"><path d="M14 5l-7 7 7 7" /></svg>
      </button>
      <div class="slbl ch">
        <strong>workspace</strong>
        <span>ringkasan &amp; sinyal</span>
      </div>
      <span class="ch" style="margin-left: auto; display: flex; align-items: center; font-size: 9px; color: var(--muted)">
        <span class="conn-dot" :class="{ live: pendakiAktif > 0 }"></span>
        <span>{{ pendakiAktif > 0 ? "live" : "waiting" }}</span>
      </span>
    </div>

    <div class="sb ch">
      <SessionsPanel />

      <!-- ringkasan -->
      <div class="pnl">
        <div class="ph"><div class="tl">ringkasan</div><div class="sv">{{ pendakiAktif > 0 ? "live" : "waiting" }}</div></div>
        <div class="pb">
          <div class="mgrid">
            <div class="mc"><strong>{{ pendakiAktif }}</strong><span>pendaki aktif</span></div>
            <div class="mc" :class="{ alert: sosAktif > 0 }"><strong>{{ sosAktif }}</strong><span>sos aktif</span></div>
            <div class="mc" :class="{ good: pdr != null && pdr >= 90, alert: pdr != null && pdr < 80 }" :title="`ambang plan: LOS ≥90%, NLOS ≥80% · ${diagStore.list.length} sesi`"><strong :style="pdr == null ? 'color: var(--muted)' : ''">{{ pdr == null ? "—" : `${pdr.toFixed(0)}%` }}</strong><span>pdr sesi</span></div>
            <div class="mc" :title="latTitle"><strong :style="lat == null ? 'color: var(--muted)' : ''">{{ latText }}</strong><span>latency e2e</span></div>
          </div>
        </div>
      </div>

      <!--
        Kartu di bawah ini (signal trend, latency timeline, RF params)
        masih placeholder murni - backend belum punya tabel/endpoint buat
        telemetry per-link (SNR, margin, PDR, latency, cuaca, SF/ToA).
        Struktur & class-nya udah final, tinggal isi datanya nanti.
      -->
      <div class="pnl">
        <div class="ph"><div class="tl">signal trend</div><div class="sv">menunggu data</div></div>
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

      <div class="pnl">
        <div class="ph"><div class="tl">latency e2e</div><div class="sv">{{ latText }}</div></div>
        <div class="pb" style="padding-bottom: 8px">
          <div class="ekg-c">
            <div class="ekg-h"><strong>timeline rolling</strong><span>—</span></div>
            <div class="ekg-w">belum ada data telemetry link masuk</div>
          </div>
        </div>
      </div>

      <div class="pnl">
        <div class="ph"><div class="tl">rf params</div><div class="sv">—</div></div>
        <div class="pb">
          <div class="rf-row">
            <div class="rf-c"><strong>kondisi cuaca</strong><span>—</span></div>
            <div class="rf-c"><strong>sf / toa</strong><span>—</span></div>
          </div>
          <div class="lgnd">
            <div class="lg"><span class="sw circle" style="background: var(--blue)"></span>hiker</div>
            <div class="lg"><span class="sw circle" style="background: var(--red)"></span>sos</div>
            <div class="lg dim"><span class="sw circle" style="background: var(--violet)"></span>relay (belum ada data)</div>
            <div class="lg dim"><span class="sw circle" style="background: var(--green)"></span>base (belum ada data)</div>
            <div class="lg dim"><span class="sw line" style="background: var(--green)"></span>link kuat (belum ada data)</div>
            <div class="lg dim"><span class="sw line" style="background: var(--amber)"></span>marginal (belum ada data)</div>
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

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const collapsed = ref(false);
const diagStore = useDiagnosticsStore();
const pdr = computed(() => diagStore.pdrOverall);
const lat = computed(() => diagStore.latencyMedianS);
// median latency antar sesi (detik). Negatif = jam laptop tidak sinkron dengan jam GPS node.
const latText = computed(() => (lat.value == null ? "—" : lat.value < 0 ? "jam?" : `${lat.value.toFixed(1)} s`));
const latTitle = computed(() => lat.value != null && lat.value < 0
  ? "Negatif: jam laptop tidak sinkron dengan waktu GPS node. Sinkronkan NTP."
  : "Median (received_at − waktu GPS node). Ambang plan: ≤15 dtk (1 hop), ≤30 dtk (2 hop).");

const pendakiAktif = computed(() => Object.keys(hikerStore.hikers).length);
const sosAktif = computed(() => alertStore.alerts.length);
const trends = ["pdr", "latency", "snr", "margin"];
</script>