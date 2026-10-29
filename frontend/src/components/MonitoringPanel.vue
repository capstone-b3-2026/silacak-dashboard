<template>
  <aside class="floating sidebar right" :class="{ collapsed }">
    <div class="sh">
      <button class="tbtn" @click="collapsed = !collapsed" :aria-expanded="!collapsed" title="Ciutkan atau buka panel" aria-label="Ciutkan atau buka panel kanan">
        <svg viewBox="0 0 24 24"><path d="M10 5l7 7-7 7" /></svg>
      </button>
      <div class="slbl ch">
        <strong>Pemantauan</strong>
        <span>Pendaki, sinyal, SOS</span>
      </div>
    </div>

    <div class="sb ch">
      <div style="display: flex; flex-direction: column; gap: 0; min-height: 0; flex: 1">
        <!-- selected hiker -->
        <div class="pnl">
          <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>Pendaki dipilih</div><div class="sv">{{ hikerStore.selectedCode || "belum ada" }}</div></div>
          <div class="pb">
            <div class="selc" v-if="selected">
              <div class="selc-top">
                <div class="selc-id">
                  <strong>{{ nameFor(hikerStore.selectedCode) || hikerStore.selectedCode }}</strong>
                  <span v-if="nameFor(hikerStore.selectedCode)" class="selc-code" title="Kode alat (hardware)">{{ hikerStore.selectedCode }}</span>
                  <span class="selc-trail">{{ selected.route_path || "langsung" }}</span>
                  <!-- Badge status pendaki dikumpulkan di kolom kiri (di bawah trail) supaya tidak menumpuk
                       di kolom kanan dan menekan angka baterai. Badge utama DINAMIS: kondisi terburuk aktual
                       (SOS merah > di luar jalur / tidak terdengar amber > Normal hijau). -->
                </div>
                <div class="selc-side">
                  <div class="selc-batt" :class="battClass(selected.battery_pct)">
                    <strong>{{ selected.battery_pct != null ? `${selected.battery_pct}%` : "—" }}</strong>
                    <span>Baterai</span>
                  </div>
                  <div class="selc-seen">{{ fmtTime(selected.recorded_at) }} · terakhir terlihat</div>
                </div>
              </div>

              <div class="selc-badges" style="padding: 14px 0 0 0">
                <span v-if="hikerStore.selectedCode" class="bdg" :class="statusFor(hikerStore.selectedCode).cls">{{ selStatusLabel }}</span>
                <span v-if="selDiag?.stale" class="bdg warn" :title="`tidak ada paket > ${selDiag.stale_after_s ?? diagStore.staleAfterS} dtk`">Tidak terdengar {{ fmtAge(selDiag.silent_s) }}</span>
                <span v-if="selected.gps_valid === false" class="bdg neutral" title="Satelit < 4, ketelitian GPS (HDOP) > 5, atau tanpa fix: posisi di peta memakai lokasi terakhir yang valid">GPS tidak valid</span>
              </div>

              <div class="selc-grid primary">
                <div class="selc-cell">
                  <strong>{{ selected.elevation != null ? `${selected.elevation} m` : "—" }}</strong>
                  <span>Ketinggian</span>
                </div>
                <div class="selc-cell">
                  <strong>{{ fmtPos(selected) }}</strong>
                  <span>Posisi</span>
                </div>
              </div>

              <div class="selc-grid secondary">
                <div class="selc-cell sm" title="Kekuatan sinyal radio yang diterima base (RSSI). Makin mendekati 0 dBm makin kuat; di bawah sekitar −110 dBm hampir putus."><strong>{{ selected.rssi_dbm != null ? `${selected.rssi_dbm} dBm` : "—" }}</strong><span>Kekuatan sinyal</span></div>
                <div class="selc-cell sm" title="Jumlah relay yang dilewati paket sebelum sampai ke base (hop). Langsung = tanpa relay."><strong>{{ hopText(selected.hop_count) }}</strong><span>Lewat relay</span></div>
                <div class="selc-cell sm" title="Jumlah satelit GPS / ketelitian GPS (HDOP). HDOP makin kecil makin teliti; di atas 5 dianggap tidak valid."><strong>{{ selected.satellites ?? "—" }} / {{ selected.hdop ?? "—" }}</strong><span>Satelit / ketelitian GPS</span></div>
                <div class="selc-cell sm"><strong>{{ selSosCount }}</strong><span>Jumlah SOS</span></div>
              </div>
            </div>
            <div class="selc" v-else>
              <div class="selr"><strong>—</strong><span style="font-size: 13px; color: var(--muted)">Klik pendaki untuk detail</span></div>
              <div class="selb">Pilih pendaki dari daftar atau klik marker di peta.</div>
            </div>
          </div>
        </div>

        <!-- tabs -->
        <div class="pnl" style="flex-shrink: 0">
          <div class="pb" style="padding: 8px 12px">
            <div class="tabs" role="tablist" aria-label="Daftar pemantauan" :style="{ '--tabs': tabs.length }">
              <button v-for="t in tabs" :key="t" class="tab" role="tab" :aria-selected="activeTab === t" :class="{ active: activeTab === t }" @click="activeTab = t">
                {{ TAB_LABELS[t] }}
                <!-- badge merah = SOS saja (merah = SOS). OFF_TRAIL amber tidak menambah angka merah ini. -->
                <span v-if="t === 'sos' && sosAlertCount" class="tab-badge">{{ sosAlertCount }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- tab: hikers -->
        <div v-if="activeTab === 'hikers'" class="pnl pnl-fill">
          <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>Daftar pendaki</div><div class="sv">{{ hikerCodes.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!hikerCodes.length" class="empty">Menunggu data…</div>
            <div v-else class="hgrid">
              <div
                v-for="(code, idx) in hikerCodes"
                :key="code"
                class="hcard"
                :class="{ sel: code === hikerStore.selectedCode, sos: sosCountFor(code) > 0 }"
                @click="hikerStore.selectHiker(code)"
              >
                <div class="ht">
                  <span class="hnum">{{ idx + 1 }}</span>
                  <div class="hid-wrap">
                    <span class="hid">{{ nameFor(code) || code }}</span>
                    <span class="hpos">
                      <template v-if="nameFor(code)">{{ code }} · </template>{{ hikerStore.hikers[code].battery_pct != null ? `${hikerStore.hikers[code].battery_pct}%` : "Baterai —" }}
                      · {{ fmtTime(hikerStore.hikers[code].recorded_at) }}
                    </span>
                  </div>
                  <span class="bdg" :class="statusFor(code).cls">{{ statusFor(code).label }}</span>
                  <svg class="hchev" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" /></svg>
                </div>
                <GpxExportButton :hiker-code="code" @click.stop />
              </div>
            </div>
          </div>
        </div>

        <!-- tab: links -->
        <div v-if="activeTab === 'links'" class="pnl pnl-fill">
          <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0" /><circle cx="12" cy="12" r="1" /></svg>Link radio aktif</div><div class="sv">{{ diagStore.list.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!diagStore.list.length" class="empty">Belum ada paket masuk dari sesi aktif</div>
            <div v-else class="lnkl">
              <div v-for="d in diagStore.list" :key="d.session_id" class="lnk" style="cursor: pointer" @click="hikerStore.selectHiker(d.hiker_code)">
                <div class="etit"><span>{{ d.hiker_code }} · {{ d.route_path || "langsung" }}</span><span class="bdg" :class="d.stale ? 'warn' : 'ok'">{{ d.stale ? `Tidak terdengar ${fmtAge(d.silent_s)}` : "Terdengar" }}</span></div>
                <div class="emeta">
                  <span title="RSSI">Kekuatan sinyal</span> {{ d.rssi_dbm ?? "—" }} dBm · {{ hopText(d.hop_count) }} · jarak ke base {{ diagStore.baseSet ? fmtDist(d.dist_to_base_m) : "(atur base di Setup lokasi)" }}<br />
                  <span title="PDR: persentase paket yang sampai ke base">Paket yang sampai</span> {{ d.pdr != null ? `${d.pdr}%` : "—" }} ({{ d.received }} diterima, {{ d.missing }} hilang) · <span title="Latency: selisih waktu paket diterima dengan waktu GPS alat">tunda data</span> {{ d.latency_p50_s != null ? `${d.latency_p50_s} dtk (p95 ${d.latency_p95_s} dtk)` : "—" }}<br />
                  GPS {{ d.gps_valid ? "valid" : "tidak valid" }} · {{ d.satellites ?? "—" }} satelit · <span title="HDOP: makin kecil makin teliti">ketelitian GPS</span> {{ d.hdop ?? "—" }} · {{ d.gps_bad_packets }} paket tanpa fix/tidak valid
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- tab: events -->
        <div v-if="activeTab === 'log'" class="pnl pnl-fill">
          <div class="ph"><div class="tl">Log paket · {{ diagStore.packetsFor || "—" }}</div><div class="sv">{{ diagStore.packets.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <RssiScatter :packets="diagStore.packets" :base-set="diagStore.baseSet" />
            <div v-if="!diagStore.packets.length" class="empty">Pilih pendaki yang sudah mengirim paket</div>
            <div v-else class="evl">
              <div v-for="p in diagStore.packets.slice(0, 60)" :key="`${p.sequence}-${p.received_at}`" class="ev">
                <div class="etit">
                  <span>#{{ p.sequence ?? "?" }} · {{ fmtClock(p.received_at) }}</span>
                  <span class="bdg" :class="p.gps_valid ? 'ok' : 'neutral'">{{ p.gps_valid ? "Ada fix GPS" : "Tanpa fix GPS" }}</span>
                </div>
                <div class="emeta">
                  <span title="RSSI">Kekuatan sinyal</span> {{ p.rssi_dbm ?? "—" }} dBm · {{ fmtDist(p.dist_to_base_m) }} · {{ p.route_path || "langsung" }} ({{ hopText(p.hop_count) }})<br />
                  {{ p.satellites ?? "—" }} satelit / <span title="HDOP">ketelitian GPS</span> {{ p.hdop ?? "—" }} · <span title="Latency">tunda data</span> {{ p.latency_s != null ? `${p.latency_s} dtk` : "—" }}<template v-if="p.missing_since_previous"> · <b style="color: var(--amber)">{{ p.missing_since_previous }} paket hilang sebelumnya</b></template>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- tab: sos -->
        <div v-if="activeTab === 'sos'" class="pnl pnl-fill">
          <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18h.01" /></svg>SOS aktif</div><div class="sv">{{ alertStore.alerts.length }}</div></div>
          <div class="pb" style="overflow-y: auto; flex: 1; min-height: 0">
            <div v-if="!alertStore.alerts.length" class="empty">Belum ada SOS</div>
            <div v-else class="sosl">
              <div v-for="a in alertStore.alerts" :key="a.id" class="sosev" :class="{ offtrail: a.alert_type === 'OFF_TRAIL' }">
                <div class="etit">
                  <span>{{ a.hiker_code }}</span>
                  <span class="bdg" :class="a.alert_type === 'OFF_TRAIL' ? 'warn' : 'bad'">{{ alertLabel(a.alert_type) }}</span>
                </div>
                <div class="emeta">
                  {{ fmtTime(a.triggered_at) }}<template v-if="a.alert_type === 'OFF_TRAIL' && a.meta?.dist_to_trail_m != null"> · {{ Math.round(a.meta.dist_to_trail_m) }} m dari jalur</template>
                </div>
                <!-- OFF_TRAIL tidak bisa disenyapkan manual: hilang sendiri saat pendaki kembali masuk perimeter -->
                <button v-if="a.alert_type !== 'OFF_TRAIL'" class="ack-btn" @click="alertStore.acknowledge(a.id)">Tandai sudah ditangani</button>
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
import { useSessionStore } from "../stores/sessions";
import { useDiagnosticsStore } from "../stores/diagnostics";
import GpxExportButton from "./GpxExportButton.vue";
import RssiScatter from "./RssiScatter.vue";
import { useUiStore } from "../stores/ui";
import { alertLabel } from "../utils/alerts";

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const sessionStore = useSessionStore();
const diagStore = useDiagnosticsStore();
const uiStore = useUiStore();
const collapsed = ref(false);

// Tampilan harian cukup daftar pendaki + SOS. Diagnostik link & log paket muncul di mode lanjutan.
const TAB_LABELS = { hikers: "Pendaki", links: "Link", log: "Log paket", sos: "SOS" };
const tabs = computed(() => (uiStore.advanced ? ["hikers", "links", "log", "sos"] : ["hikers", "sos"]));
const activeTab = ref("hikers");
watch(tabs, (t) => {
  if (!t.includes(activeTab.value)) activeTab.value = "hikers";
});
function hopText(n) {
  if (n == null) return "—";
  return n === 0 ? "Langsung" : `${n} relay`;
}

// selectedCode HIDUP DI STORE (bukan ref lokal lagi), biar MapView.vue
// bisa baca & ikut nge-highlight marker yang sama - satu sumber
// kebenaran buat "siapa yang lagi dipilih monitor", dua arah.
const hikerCodes = computed(() => Object.keys(hikerStore.hikers).sort((a, b) => a.localeCompare(b)));
const selected = computed(() => (hikerStore.selectedCode ? hikerStore.hikers[hikerStore.selectedCode] : null));

// Peta kode alat -> nama pendaki dari sesi aktif (join di frontend, tanpa ubah backend/SSE).
// Sesi yang dibuka otomatis (alat kirim data sebelum check-in) full_name-nya kosong -> jatuh ke kode.
const codeToName = computed(() => {
  const m = {};
  for (const s of sessionStore.active) {
    if (s.hiker_code && s.full_name) m[s.hiker_code] = s.full_name;
  }
  return m;
});
// Nama pendaki bila ada, selain itu null (pemanggil pakai kode alat sebagai judul cadangan).
function nameFor(code) {
  return (code && codeToName.value[code]) || null;
}

// SOS merah = MANUAL_SOS/STAGNANT. OFF_TRAIL (amber) TIDAK ikut hitungan SOS: kartu/badge pendaki
// tidak boleh menyala merah karena di luar jalur (merah = SOS saja).
function sosCountFor(code) {
  return alertStore.alerts.filter((a) => a.hiker_code === code && a.alert_type !== "OFF_TRAIL").length;
}
const selSosCount = computed(() => (hikerStore.selectedCode ? sosCountFor(hikerStore.selectedCode) : 0));
// Label badge utama panel kanan: pakai statusFor, tapi "OK" diganti "Normal" agar sesuai gaya panel detail.
const selStatusLabel = computed(() => {
  if (!hikerStore.selectedCode) return "";
  const s = statusFor(hikerStore.selectedCode);
  return s.label === "OK" ? "Normal" : s.label;
});
// Jumlah alarm SOS (merah) untuk badge merah tab, OFF_TRAIL dikecualikan.
const sosAlertCount = computed(() => alertStore.alerts.filter((a) => a.alert_type !== "OFF_TRAIL").length);
// Kode alat yang punya alarm OFF_TRAIL aktif -> badge amber "Di luar jalur" (hilang saat alarm di-resolve).
const offTrailCodes = computed(
  () => new Set(alertStore.alerts.filter((a) => a.alert_type === "OFF_TRAIL").map((a) => a.hiker_code))
);

// Badge status pendaki DINAMIS: menampilkan kondisi TERBURUK yang aktual, bukan sekadar "OK" hijau.
// Urutan keparahan: SOS (merah) > di luar jalur / tidak terdengar (amber) > OK (hijau).
// Merah HANYA untuk SOS (OFF_TRAIL & stale = amber). Dipakai sama di kartu daftar dan panel pendaki terpilih
// supaya kedua tempat tidak pernah bertentangan (dulu "OK" hijau bisa muncul padahal pendaki di luar jalur).
function statusFor(code) {
  if (sosCountFor(code) > 0) return { label: "SOS", cls: "bad" };
  if (offTrailCodes.value.has(code)) return { label: "Di luar jalur", cls: "warn" };
  if (diagStore.sessions[code]?.stale) return { label: "Tidak terdengar", cls: "warn" };
  return { label: "OK", cls: "ok" };
}

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

<style scoped>
/* Cuaca & Kontrol dihapus -> sisa 4 sel (sinyal, relay, satelit, jumlah SOS) ditata 2x2 agar rapat tanpa sel yatim */
.selc-grid.secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
/* Kode alat (H01) sebagai subjudul kecil di bawah nama pendaki: operator tetap bisa rujuk-silang perangkat. */
.selc-code { font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: 0.02em; }
.sosev .ack-btn { background: var(--red); color: #fff; }
.sosev .ack-btn:hover:not(:disabled) { background: var(--red); filter: brightness(0.92); }
/* OFF_TRAIL = peringatan amber, BUKAN merah (merah = SOS saja). Aksen kiri + latar amber lembut. */
.sosev.offtrail { border-left-color: var(--amber); background: var(--amber-glow); }
</style>