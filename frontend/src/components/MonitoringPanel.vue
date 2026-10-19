<template>
  <aside class="floating sidebar right" :class="{ collapsed }">
    <div class="sh">
      <button class="tbtn" @click="collapsed = !collapsed" title="Collapse sidebar">
        <svg viewBox="0 0 24 24"><path d="M10 5l7 7-7 7" /></svg>
      </button>
      <div class="slbl ch">
        <strong>monitoring</strong>
        <span>hiker, lora, sos</span>
      </div>
    </div>

    <div class="sb ch">
      <div style="display: flex; flex-direction: column; gap: 7px; min-height: 0; flex: 1">
        <!-- selected hiker -->
        <div class="pnl">
          <div class="ph"><div class="tl">selected hiker</div><div class="sv">{{ hikerStore.selectedCode || "none" }}</div></div>
          <div class="pb">
            <div class="selc" v-if="selected">
              <div class="selc-top">
                <div class="selc-id">
                  <strong>{{ hikerStore.selectedCode }}</strong>
                  <span class="selc-trail">{{ selected.route_path || "langsung" }}</span>
                </div>
                <div class="selc-side">
                  <span class="bdg" :class="selSosCount > 0 ? 'bad' : 'ok'">{{ selSosCount > 0 ? "sos" : "normal" }}</span>
                  <span v-if="selDiag?.stale" class="bdg bad" :title="`tidak ada paket > ${selDiag.stale_after_s ?? diagStore.staleAfterS} dtk`">tidak terdengar {{ fmtAge(selDiag.silent_s) }}</span>
                  <span v-if="selected.gps_valid === false" class="bdg bad" title="Nsat < 4, HDOP > 5, atau tanpa fix: posisi di peta = lokasi terakhir">gps invalid · lokasi terakhir</span>
                  <div class="selc-batt" :class="battClass(selected.battery_pct)">
                    <strong>{{ selected.battery_pct != null ? `${selected.battery_pct}%` : "—" }}</strong>
                    <span>baterai</span>
                  </div>
                  <div class="selc-seen">{{ fmtTime(selected.recorded_at) }} · terakhir terlihat</div>
                </div>
              </div>

              <div class="selc-grid primary">
                <div class="selc-cell">
                  <strong>{{ selected.elevation != null ? `${selected.elevation} m` : "—" }}</strong>
                  <span>ketinggian</span>
                </div>
                <div class="selc-cell">
                  <strong>{{ fmtPos(selected) }}</strong>
                  <span>posisi</span>
                </div>
              </div>

              <div class="selc-grid secondary">
                <div class="selc-cell sm"><strong>{{ selected.rssi_dbm != null ? `${selected.rssi_dbm} dBm` : "—" }}</strong><span>rssi</span></div>
                <div class="selc-cell sm"><strong>{{ selected.hop_count ?? "—" }}</strong><span>hop</span></div>
                <div class="selc-cell sm"><strong>{{ selected.satellites ?? "—" }} / {{ selected.hdop ?? "—" }}</strong><span>gps sat/hdop</span></div>
                <div class="selc-cell sm"><strong class="placeholder">—</strong><span>cuaca</span></div>
                <div class="selc-cell sm"><strong class="placeholder">—</strong><span>kontrol</span></div>
                <div class="selc-cell sm"><strong>{{ selSosCount }}</strong><span>sos count</span></div>
              </div>
            </div>
            <div class="selc" v-else>
              <div class="selr"><strong>—</strong><span style="font-size: 9px; color: var(--muted)">klik pendaki untuk detail</span></div>
              <div class="selb">Pilih pendaki dari daftar atau klik marker di peta.</div>
            </div>
          </div>
        </div>

        <!-- tabs -->
        <div class="pnl" style="flex-shrink: 0">
          <div class="pb" style="padding: 5px 7px">
            <div class="tabs">
              <button v-for="t in tabs" :key="t" class="tab" :class="{ active: activeTab === t }" @click="activeTab = t">
                {{ t }}
                <span v-if="t === 'sos' && alertStore.alerts.length" class="tab-badge">{{ alertStore.alerts.length }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- tab: hikers -->
        <div v-if="activeTab === 'hikers'" class="pnl pnl-fill">
          <div class="ph"><div class="tl">daftar pendaki</div><div class="sv">{{ hikerCodes.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!hikerCodes.length" class="empty">menunggu data…</div>
            <div v-else class="hgrid">
              <div
                v-for="code in hikerCodes"
                :key="code"
                class="hcard"
                :class="{ sel: code === hikerStore.selectedCode, sos: sosCountFor(code) > 0 }"
                @click="hikerStore.selectHiker(code)"
              >
                <div class="ht">
                  <span class="hid">{{ code }}</span>
                  <span class="bdg" :class="sosCountFor(code) > 0 ? 'bad' : 'ok'">{{ sosCountFor(code) > 0 ? "sos" : "ok" }}</span>
                </div>
                <div class="hpos">
                  {{ hikerStore.hikers[code].battery_pct != null ? `${hikerStore.hikers[code].battery_pct}%` : "bat —" }}
                  · {{ fmtTime(hikerStore.hikers[code].recorded_at) }}
                </div>
                <GpxExportButton :hiker-code="code" @click.stop />
              </div>
            </div>
          </div>
        </div>

        <!-- tab: links -->
        <div v-if="activeTab === 'links'" class="pnl pnl-fill">
          <div class="ph"><div class="tl">link lora aktif</div><div class="sv">{{ diagStore.list.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!diagStore.list.length" class="empty">belum ada paket masuk dari sesi aktif</div>
            <div v-else class="lnkl">
              <div v-for="d in diagStore.list" :key="d.session_id" class="lnk" style="cursor: pointer" @click="hikerStore.selectHiker(d.hiker_code)">
                <div class="etit"><span>{{ d.hiker_code }} · {{ d.route_path || "langsung" }}</span><span class="bdg" :class="d.stale ? 'bad' : 'ok'">{{ d.stale ? `diam ${fmtAge(d.silent_s)}` : "terdengar" }}</span></div>
                <div class="emeta">
                  rssi {{ d.rssi_dbm ?? "—" }} dBm · {{ d.hop_count ?? "—" }} hop · jarak ke base {{ diagStore.baseSet ? fmtDist(d.dist_to_base_m) : "(set base di Setup)" }}<br />
                  pdr {{ d.pdr != null ? `${d.pdr}%` : "—" }} ({{ d.received }} diterima, {{ d.missing }} hilang) · latency {{ d.latency_p50_s != null ? `${d.latency_p50_s} s (p95 ${d.latency_p95_s} s)` : "—" }}<br />
                  gps {{ d.gps_valid ? "valid" : "invalid" }} · {{ d.satellites ?? "—" }} sat / hdop {{ d.hdop ?? "—" }} · {{ d.gps_bad_packets }} paket tanpa fix/invalid
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- tab: events -->
        <div v-if="activeTab === 'log'" class="pnl pnl-fill">
          <div class="ph"><div class="tl">packet log · {{ diagStore.packetsFor || "—" }}</div><div class="sv">{{ diagStore.packets.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <RssiScatter :packets="diagStore.packets" :base-set="diagStore.baseSet" />
            <div v-if="!diagStore.packets.length" class="empty">pilih pendaki yang sudah mengirim paket</div>
            <div v-else class="evl">
              <div v-for="p in diagStore.packets.slice(0, 60)" :key="`${p.sequence}-${p.received_at}`" class="ev">
                <div class="etit">
                  <span>#{{ p.sequence ?? "?" }} · {{ fmtClock(p.received_at) }}</span>
                  <span class="bdg" :class="p.gps_valid ? 'ok' : 'bad'">{{ p.gps_valid ? "fix" : "tanpa fix" }}</span>
                </div>
                <div class="emeta">
                  rssi {{ p.rssi_dbm ?? "—" }} dBm · {{ fmtDist(p.dist_to_base_m) }} · {{ p.route_path || "langsung" }} ({{ p.hop_count ?? "—" }} hop)<br />
                  {{ p.satellites ?? "—" }} sat / hdop {{ p.hdop ?? "—" }} · latency {{ p.latency_s != null ? `${p.latency_s} s` : "—" }}<template v-if="p.missing_since_previous"> · <b style="color: var(--red)">{{ p.missing_since_previous }} hilang sebelumnya</b></template>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- tab: sos -->
        <div v-if="activeTab === 'sos'" class="pnl pnl-fill">
          <div class="ph"><div class="tl">sos aktif</div><div class="sv">{{ alertStore.alerts.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!alertStore.alerts.length" class="empty">belum ada sos 👍</div>
            <div v-else class="sosl">
              <div v-for="a in alertStore.alerts" :key="a.id" class="sosev">
                <div class="etit"><span>{{ a.hiker_code }}</span><span class="bdg bad">🆘 {{ a.alert_type }}</span></div>
                <div class="emeta">{{ fmtTime(a.triggered_at) }}</div>
                <button class="ack-btn" @click="alertStore.acknowledge(a.id)">Acknowledge</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useHikerStore } from "../stores/hikers";
import { useAlertStore } from "../stores/alerts";
import { useDiagnosticsStore } from "../stores/diagnostics";
import GpxExportButton from "./GpxExportButton.vue";
import RssiScatter from "./RssiScatter.vue";

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const diagStore = useDiagnosticsStore();
const collapsed = ref(false);

const tabs = ["hikers", "links", "log", "sos"];
const activeTab = ref("hikers");

// selectedCode HIDUP DI STORE (bukan ref lokal lagi), biar MapView.vue
// bisa baca & ikut nge-highlight marker yang sama - satu sumber
// kebenaran buat "siapa yang lagi dipilih monitor", dua arah.
const hikerCodes = computed(() => Object.keys(hikerStore.hikers).sort((a, b) => a.localeCompare(b)));
const selected = computed(() => (hikerStore.selectedCode ? hikerStore.hikers[hikerStore.selectedCode] : null));

function sosCountFor(code) {
  return alertStore.alerts.filter((a) => a.hiker_code === code).length;
}
const selSosCount = computed(() => (hikerStore.selectedCode ? sosCountFor(hikerStore.selectedCode) : 0));

watch(
  hikerCodes,
  (codes) => {
    if (!hikerStore.selectedCode && codes.length) hikerStore.selectHiker(codes[0]);
  },
  { immediate: true }
);

function battClass(pct) {
  if (pct == null) return "";
  if (pct >= 60) return "hi";
  if (pct >= 20) return "mid";
  return "lo";
}

const selDiag = computed(() => (hikerStore.selectedCode ? diagStore.sessions[hikerStore.selectedCode] : null));
function fmtDist(m) {
  if (m == null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}
function fmtAge(s) {
  if (s == null) return "";
  return s >= 3600 ? `${Math.floor(s / 3600)} j` : s >= 60 ? `${Math.floor(s / 60)} mnt` : `${Math.round(s)} dtk`;
}
function fmtClock(ts) {
  return new Date(ts).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtPos(h) {
  if (h.lat == null || h.lon == null) return "—";
  return `${h.lat.toFixed(4)}, ${h.lon.toFixed(4)}`;
}
function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}
</script>