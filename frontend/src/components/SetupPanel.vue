<template>
  <aside class="setup floating">
    <div class="sh">
      <div class="slbl"><strong>Setup</strong><span>Lokasi, DEM &amp; perangkat</span></div>
      <button class="tbtn" @click="site.showSetup = false; site.editMode = null" title="Tutup">
        <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
      </button>
    </div>

    <div class="stabs">
      <button :class="{ on: tab === 'site' }" @click="tab = 'site'; showAdvanced = false">Lokasi &amp; relay</button>
      <button :class="{ on: tab === 'dev' }" @click="tab = 'dev'">
        Perangkat<i v-if="dev.outOfSync.length" class="dot"></i>
      </button>
    </div>

    <!-- ═════════ TAB LOKASI ═════════ -->
    <div v-if="tab === 'site' && !showAdvanced" class="sb">
      <p v-if="site.error" class="err" style="margin: 6px 12px">{{ site.error }}</p>

      <!-- 1. DEM -->
      <section class="pnl">
        <div class="ph"><span class="tl">1 · DEM (GeoTIFF)</span>
          <span v-if="site.site" class="chip" :class="site.site.status">{{ statusLabel }}</span>
        </div>
        <div class="pb">
          <template v-if="site.processing">
            <div class="bar"><div></div></div>
            <p class="hint">
              {{ site.site.pending?.message || site.site.message || "Memproses…" }}
              <template v-if="site.site.pending">DEM lama tetap dipakai sampai yang baru selesai.</template>
              Proses jalan di server, aman kalau halaman ditutup.
            </p>
          </template>

          <template v-else>
            <div v-if="site.pendingError" class="err">
              Upload terakhir gagal: {{ site.pendingError }}
              <br /><b>DEM lama masih aktif dan tidak berubah.</b>
              <button class="btn sm" style="margin-top:6px" @click="site.dismissError()">Tutup</button>
            </div>
            <div v-if="site.site?.status === 'error'" class="err">Gagal: {{ site.site.message }}</div>
            <div v-else-if="site.ready" class="kv">
              <div><span>Lokasi</span><b>{{ site.site.name }}</b></div>
              <div><span>Resolusi</span><b>{{ site.site.dem_info.res_m }} m/piksel</b></div>
              <div><span>Elevasi</span><b>{{ site.site.dem_info.elev_min }} – {{ site.site.dem_info.elev_max }} m</b></div>
              <div><span>Tile 3D</span><b>{{ site.site.dem_info.tiles }} (z{{ site.site.dem_info.min_zoom }}–{{ site.site.dem_info.max_zoom }})</b></div>
              <div><span>Peta topo offline</span><b :class="site.site.dem_info.topo ? 'ok' : 'muted'">{{ site.site.dem_info.topo ? "siap" : "sedang dibuat di server…" }}</b></div>
              <p v-for="n in site.site.dem_info.notes" :key="n" class="hint">{{ n }}</p>
            </div>

            <div
              class="drop" :class="{ over: dragOver }"
              @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop"
              @click="fileInput.click()"
            >
              <input ref="fileInput" type="file" accept=".tif,.tiff" hidden @change="onPick" />
              <template v-if="picked">
                <b>{{ picked.name }}</b><span>{{ (picked.size / 1048576).toFixed(1) }} MB</span>
              </template>
              <template v-else>
                <b>{{ site.site ? "Ganti DEM" : "Tarik file .tif ke sini" }}</b><span>atau klik untuk pilih file</span>
              </template>
            </div>
            <input v-model="siteName" class="inp" placeholder="Nama lokasi (mis. Bukit Klangon)" />
            <button class="btn primary" :disabled="!picked || site.busy" @click="doUpload">
              {{ site.busy ? "Mengunggah…" : "Upload & proses otomatis" }}
            </button>
            <p class="hint">Cukup satu file. CRS kosong / UTM, nodata, dan tile 3D diurus otomatis. Titik base &amp; trail lama ikut terbawa.</p>
          </template>
        </div>
      </section>

      <template v-if="site.ready">
        <!-- 2. base & trail -->
        <section class="pnl">
          <div class="ph"><span class="tl">2 · Titik base &amp; trail</span></div>
          <div class="pb">
            <div class="row">
              <div class="grow">
                <span class="lbl">Base station</span>
                <b v-if="site.site.base">{{ site.site.base.lat.toFixed(5) }}, {{ site.site.base.lon.toFixed(5) }}</b>
                <b v-else class="muted">belum diisi</b>
              </div>
              <button class="btn" :class="{ active: site.editMode === 'base' }" @click="toggleEdit('base')">
                {{ site.editMode === "base" ? "Klik peta…" : "Pilih di peta" }}
              </button>
            </div>
            <div class="row">
              <div class="grow">
                <span class="lbl">Jalur pendakian</span>
                <b>{{ site.site.trail.length }} titik</b>
              </div>
              <button class="btn" :class="{ active: site.editMode === 'trail' }" @click="toggleEdit('trail')">
                {{ site.editMode === "trail" ? "Selesai" : "Gambar di peta" }}
              </button>
            </div>
            <div class="dist" v-if="trailDist.segments.length">
              <div class="dist-head">
                <span class="lbl">Jarak horizontal</span>
                <b>{{ (trailDist.totalM / 1000).toFixed(2) }} km</b>
                <button class="lnk" type="button" @click="showSegments = !showSegments">
                  {{ showSegments ? "sembunyikan rincian" : "rincian segmen" }}
                </button>
              </div>
              <!-- Angka 3D sekunder (profil dari DEM). Sembunyi bila DEM belum siap / belum terhitung;
                   angka horizontal di atas tetap tampil. -->
              <div class="dist-sub" v-if="site.trail3d">
                <span class="lbl">profil (dari DEM)</span>
                <b v-if="trail3dText">{{ trail3dText }}</b>
                <span class="note" v-if="site.trail3d.incomplete">sebagian jalur di luar cakupan DEM</span>
              </div>
              <ul v-if="showSegments" class="seg">
                <li v-for="(s, i) in trailDist.segments" :key="i">
                  <span>{{ s.fromLabel }} &rarr; {{ s.toLabel }}</span>
                  <span>{{ fmtDist(s.m) }}</span>
                </li>
              </ul>
            </div>
            <!-- Ringkasan relay: SELALU tampil. Tombol "Hitung relay" dinonaktifkan secara visual
                 bila trail belum cukup; klik paksa memunculkan notice. Relay tetap keluaran planner
                 (runPlan) - tidak ada penempatan manual di sini. -->
            <div class="row">
              <div class="grow">
                <span class="lbl">Relay</span>
                <b v-if="relayCoverage.hasPlan">
                  <span class="chip" :class="relayCoverage.statusClass">{{ relayCoverage.text }}</span>
                  <span class="relay-count">· {{ relayCoverage.relays }} relay</span>
                </b>
                <b v-else class="muted">belum dihitung</b>
              </div>
              <button
                v-if="!relayCoverage.hasPlan"
                class="btn sm"
                :class="{ 'is-off': !relayCoverage.canPlan }"
                :disabled="site.busy"
                @click="tryRunPlan()"
              >
                {{ site.busy ? "Menghitung…" : "Hitung relay" }}
              </button>
            </div>
            <div class="row" v-if="site.site.trail.length">
              <button class="btn sm" @click="site.undoTrail()">Undo titik</button>
              <button class="btn sm danger" @click="site.clearTrail()">Hapus trail</button>
            </div>
            <p v-if="site.editMode" class="hint hot">
              {{ site.editMode === "base" ? "Klik satu titik di peta untuk menaruh base." : "Klik di peta berurutan dari base ke arah puncak." }}
            </p>
          </div>
        </section>

        <!-- Langkah 3–5 disembunyikan di halaman "Konfigurasi Lanjutan" -->
        <section class="pnl">
          <div class="pb">
            <button class="btn adv-open" type="button" @click="openAdvanced">
              <span>Konfigurasi Lanjutan (Advanced)</span><span aria-hidden="true">&rsaquo;</span>
            </button>
          </div>
        </section>
      </template>
    </div>

    <!-- ═════════ KONFIGURASI LANJUTAN (langkah 3–5) ═════════ -->
    <SetupAdvanced v-else-if="tab === 'site'" @back="showAdvanced = false" />

    <!-- ═════════ TAB PERANGKAT ═════════ -->
    <div v-else class="sb">
      <p v-if="dev.error" class="err" style="margin: 6px 12px">{{ dev.error }}</p>
      <!--
      <p v-if="!cfgOn" class="hint" style="padding: 14px 0 0 14px">
        Push konfigurasi dimatikan: firmware base saat ini belum menerima perintah dari dashboard, jadi nilai di bawah hanya
        tersimpan sebagai katalog di dashboard dan tidak mengubah alat.
      </p>
      -->

      <section class="pnl">
        <div class="ph"><span class="tl">Daftar perangkat</span>
          <!--
          <button class="btn sm" :disabled="!cfgOn || !dev.outOfSync.length || dev.busy" @click="dev.pushAll()">
            Push semua ({{ dev.outOfSync.length }})
          </button>
          -->
        </div>
        <div class="pb">
          <p v-if="!dev.devices.length" class="hint">Belum ada perangkat. Tambahkan di bawah.</p>
          <div v-for="d in dev.devices" :key="d.id" class="dev">
            <div class="dev-top">
              <span class="nid">{{ d.node_id }}</span>
              <div class="grow"><b>{{ d.name }}</b><span class="lbl">{{ d.role }}<template v-if="d.hiker_code"> · {{ d.hiker_code }}</template></span></div>
              <!-- 
              <span class="chip" :class="syncClass(d)">{{ syncLabel(d) }}</span>
              -->
            </div>
            <!--
            <div class="dev-cfg">
              lapor {{ d.config.report_interval_s }} dtk · TX {{ d.config.tx_power_dbm }} dBm · {{ d.config.air_data_rate }} kbps
            </div>
            -->
            <div v-if="d.role === 'relay'" class="dev-slot">
              <span class="lbl">Dipasang di posisi</span>
              <select
                class="inp"
                :value="d.plan_slot ?? ''"
                :disabled="dev.busy"
                @change="dev.setSlot(d.id, $event.target.value === '' ? null : Number($event.target.value))"
              >
                <option value="">belum dipetakan</option>
                <option v-for="n in slotChoices(d)" :key="n" :value="n">R{{ n }}</option>
              </select>
              <span v-if="!slotOptions.length" class="hint">Hitung rencana relay dulu di tab Lokasi.</span>
            </div>
            <p v-if="d.last_command?.status === 'failed' && d.last_command.error" class="err sm">{{ d.last_command.error }}</p>
            <div class="row">
              <button class="btn sm primary" :disabled="!cfgOn || dev.busy || pushing(d)" @click="dev.push(d.id)">
                {{ !cfgOn ? "Push dimatikan" : pushing(d) ? "Menunggu bridge…" : "Push ke alat" }}
              </button>
              <button class="btn sm" @click="edit(d)">Edit</button>
              <button class="btn sm danger" @click="askRemove(d)">Hapus</button>
            </div>
          </div>
        </div>
      </section>

      <section class="pnl">
        <div class="ph"><span class="tl">{{ editId ? "Edit perangkat" : "Tambah perangkat" }}</span></div>
        <div class="pb grid2">
          <label><span class="lbl">Node ID (firmware)</span><input class="inp" type="number" min="1" max="254" v-model.number="form.node_id" /></label>
          <label><span class="lbl">Peran</span>
            <select class="inp" v-model="form.role"><option>tracker</option><option>relay</option><option>base</option></select>
          </label>
          <label class="wide"><span class="lbl">Nama</span><input class="inp" v-model="form.name" placeholder="mis. Tracker Andi" /></label>
          <!-- 
          <label><span class="lbl">Interval lapor (dtk)<ParamTip>Selang node mengirim posisi. MISMATCH: firmware _optimized mengirim kontinu (jeda minimum 300 ms), _real tiap 5000 ms; angka '30 dtk' TIDAK ada di firmware. Lagipula downlink konfigurasi belum dimengerti firmware, jadi nilai ini BELUM sampai ke alat.</ParamTip></span><input class="inp" type="number" v-model.number="form.config.report_interval_s" /></label>
          <label><span class="lbl">TX power (dBm)<ParamTip>Daya pancar node. MISMATCH: alat memakai POWER_22 = 22 dBm hardcoded; batas form ini (2–20) bahkan tak bisa mencapai 22. Downlink konfigurasi belum jalan, jadi nilai ini BELUM mengubah alat.</ParamTip></span><input class="inp" type="number" v-model.number="form.config.tx_power_dbm" /></label>
          <label><span class="lbl">Air data rate<ParamTip>Laju data radio gabungan modul E220. Pada E220 (chip LLCC68), SF, bandwidth, dan coding rate TIDAK bisa diatur terpisah — hanya satu setelan air data rate. Firmware saat ini memakai 2,4 kbps (AIR_DATA_RATE_010_24); nilai lebih rendah = jangkauan/ketahanan lebih baik tetapi lebih lambat. C-251 §2.2.1 membahas SF5–SF11 sebagai konsep simulasi, bukan knob terpisah di modul ini. MISMATCH: downlink konfigurasi belum dimengerti firmware, jadi nilai ini masih katalog dashboard dan BELUM sampai ke alat.</ParamTip></span>
            <select class="inp" v-model.number="form.config.air_data_rate">
              <option v-for="r in AIR_DATA_RATES" :key="r" :value="r">{{ r }} kbps</option>
            </select>
          </label>
          -->
          <div class="row wide">
            <button class="btn primary grow" :disabled="dev.busy || !form.name || !form.node_id" @click="submit">
              {{ editId ? "Simpan perubahan" : "Tambah" }}
            </button>
            <button v-if="editId" class="btn" @click="resetForm">Batal</button>
          </div>
          <!--
          <p class="hint wide">
            Menyimpan hanya mengubah data di dashboard. <b>Push</b> memasukkan perintah ke antrean; bridge serial di PC base
            yang mengirimnya ke alat dan mengonfirmasi balik. Tanpa bridge yang jalan, status tertahan di “menunggu bridge”.
          </p>
          -->
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useSiteStore } from "../stores/site";
import { useDeviceStore } from "../stores/devices";
import { useBaseStore } from "../stores/base";
import { trailSegments } from "../utils/routeGeo";
import ParamTip from "./ParamTip.vue";
import SetupAdvanced from "./SetupAdvanced.vue";

const site = useSiteStore();
const dev = useDeviceStore();
// Push konfigurasi hanya jalan kalau backend melaporkan firmware base mendukung CFG (FIRMWARE_SUPPORTS_CFG). Bawaan: mati.
const baseStatus = useBaseStore();
const cfgOn = computed(() => baseStatus.status?.cfg_downlink === true);
const tab = ref("site");
// Langkah 3–5 (parameter, hasil relay, kalibrasi) ada di halaman terpisah; tertutup secara bawaan.
const showAdvanced = ref(false);
function openAdvanced() {
  site.editMode = null; // hentikan mode klik-peta supaya klik peta tidak menambah titik tanpa sengaja
  showAdvanced.value = true;
}

// ── lokasi ──
const fileInput = ref(null);
const picked = ref(null);
const siteName = ref("");
const dragOver = ref(false);

// Jarak horizontal trail (great-circle Haversine, konsisten dengan backend). Reaktif: dihitung ulang
// tiap base/trail berubah karena handleMapClick/undoTrail/clearTrail mengganti array dengan salinan baru.
const trailDist = computed(() => trailSegments(site.site?.base, site.site?.trail || []));
const showSegments = ref(false);
// Format jarak ramah operator: meter bila < 1 km, selebihnya km 2 desimal.
function fmtDist(m) {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(2)} km`;
}
// Angka 3D sekunder (profil dari DEM). null bila belum terhitung atau seluruh total tak tersedia
// (mis. semua segmen di luar DEM) -> baris memakai catatan saja.
const trail3dText = computed(() => {
  const m = site.trail3d?.total_3d_m;
  return m == null ? null : fmtDist(m);
});

// Ringkasan coverage relay untuk langkah 2. Teks & kelas chip DISALIN PERSIS dari SetupAdvanced langkah 4
// supaya keduanya tidak pernah berbeda. Bila belum ada plan, tentukan apakah tombol "Hitung relay"
// layak muncul (syarat sama dengan runPlan: base ada DAN trail minimal 2 titik).
const relayCoverage = computed(() => {
  const plan = site.site?.plan;
  if (!plan) {
    const canPlan = !!site.site?.base && (site.site?.trail?.length || 0) >= 2;
    return { hasPlan: false, canPlan };
  }
  return {
    hasPlan: true,
    text: plan.covers_all ? "trail tercover" : `${plan.uncovered_points} titik belum tercover`,
    statusClass: plan.covers_all ? "ready" : "error",
    relays: plan.relays.length,
  };
});

// Tombol "Hitung relay" SELALU tampil (meski trail belum ada) tapi dinonaktifkan secara visual.
// Kalau dipaksa klik saat syarat belum terpenuhi, tampilkan notice, bukan diam saja.
function tryRunPlan() {
  if (!relayCoverage.value.canPlan) {
    site.error = "Isi jalur pendakian dulu (base + minimal 2 titik) sebelum menghitung relay.";
    return;
  }
  site.runPlan();
}

const statusLabel = computed(
  () => ({ processing: "memproses", ready: "siap", error: "gagal" }[site.site?.status] || site.site?.status)
);
function setFile(f) {
  if (!f) return;
  if (!/\.tiff?$/i.test(f.name)) {
    site.error = "File harus GeoTIFF (.tif / .tiff).";
    return;
  }
  site.error = null;
  picked.value = f;
  if (!siteName.value) siteName.value = f.name.replace(/\.tiff?$/i, "").replace(/[_-]+/g, " ");
}
const onPick = (e) => setFile(e.target.files[0]);
function onDrop(e) {
  dragOver.value = false;
  setFile(e.dataTransfer.files[0]);
}
async function doUpload() {
  await site.upload(picked.value, siteName.value || "Lokasi baru");
  picked.value = null;
  siteName.value = "";
  if (fileInput.value) fileInput.value.value = "";
}
function toggleEdit(mode) {
  site.editMode = site.editMode === mode ? null : mode;
}

// ── perangkat ──
// Relay dipetakan ke posisi R<n> dari rencana lokasi supaya rute paket ("R5>R6") bisa digambar di peta.
const slotOptions = computed(() => (site.site?.plan?.relays || []).map((r) => r.n));
function slotChoices(d) {
  const set = new Set(slotOptions.value);
  if (d.plan_slot != null) set.add(d.plan_slot); // rencana dihitung ulang: tetap tampilkan pilihan lama agar kelihatan
  return [...set].sort((a, b) => a - b);
}
// E220 (chip LLCC68) hanya punya satu setelan air data rate gabungan; ini 6 nilai kbps berbeda yang
// bermakna (lihat enum pustaka EByte). Bukan SF numerik. Default 2,4 kbps = AIR_DATA_RATE_010_24 firmware.
const AIR_DATA_RATES = [2.4, 4.8, 9.6, 19.2, 38.4, 62.5];
const emptyForm = () => ({ node_id: null, name: "", role: "tracker", config: { report_interval_s: 30, tx_power_dbm: 17, air_data_rate: 2.4 } });
const form = reactive(emptyForm());
const editId = ref(null);

function resetForm() {
  Object.assign(form, emptyForm());
  editId.value = null;
}
function edit(d) {
  editId.value = d.id;
  // Baris lama bisa membawa `sf` basi (sebelum rename ke air_data_rate). Buang supaya tidak ikut
  // tersimpan ulang; d.config sudah mengandung air_data_rate default dari _out() backend.
  const { sf, ...cfg } = d.config;
  Object.assign(form, { node_id: d.node_id, name: d.name, role: d.role, config: { ...cfg } });
}
async function submit() {
  if (await dev.save(form, editId.value)) resetForm();
}
function askRemove(d) {
  if (confirm(`Hapus perangkat "${d.name}" (node ${d.node_id})?`)) dev.remove(d.id);
}
const pushing = (d) => ["pending", "sent"].includes(d.last_command?.status);
function syncLabel(d) {
  const s = d.last_command?.status;
  if (s === "pending") return "menunggu bridge";
  if (s === "sent") return "terkirim";
  if (s === "failed" && !d.in_sync) return "gagal";
  return d.in_sync ? "tersinkron" : "belum di-push";
}
function syncClass(d) {
  const s = d.last_command?.status;
  if (s === "failed" && !d.in_sync) return "error";
  if (pushing(d)) return "processing";
  return d.in_sync ? "ready" : "warn";
}

onMounted(() => dev.load());
onBeforeUnmount(() => dev.stop());
</script>

<style scoped>
.setup { top: var(--top); bottom: var(--edge); right: var(--edge); width: 440px; max-width: 100vw; z-index: 40; border-radius: var(--radius); box-shadow: var(--shadow-pop); display: flex; flex-direction: column; overflow: hidden; color: var(--text); }
.stabs { display: flex; gap: 6px; padding: 10px 12px 0; }
.stabs button { flex: 1; height: 40px; border-radius: 9px; border: 1px solid var(--line-2); background: transparent; color: var(--text-2); font: 600 14px var(--font); cursor: pointer; position: relative; }
.stabs button.on { background: var(--accent-glow); color: var(--text); border-color: var(--accent); }
.dot { position: absolute; top: 8px; right: 10px; width: 8px; height: 8px; border-radius: 50%; background: var(--red); }

.pb { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 10px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.grid2 .wide, .wide { grid-column: 1 / -1; }
.row { display: flex; align-items: center; gap: 8px; }
.grow { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.lbl { font-size: 14px; color: var(--text-2); font-weight: 600; }
.muted { color: var(--muted); font-weight: 500; }
b.ok { color: var(--green); }
b { font-size: 15px; font-weight: 600; color: var(--text); }
label { display: flex; flex-direction: column; gap: 5px; }

.inp { width: 100%; height: 38px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--text); padding: 0 10px; font: 14px var(--font); outline: none; }
.inp:focus { border-color: var(--accent); }

.btn { height: 38px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--line-3); background: var(--panel-3); color: var(--text); font: 600 14px var(--font); cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
.btn:hover:not(:disabled) { border-color: var(--accent); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--btn); border-color: var(--btn); color: var(--on-btn); }
.btn.primary:hover:not(:disabled) { background: var(--btn-hover); border-color: var(--btn-hover); }
.btn.active { background: var(--btn-alt); border-color: var(--btn-alt); color: var(--on-btn-alt); }
.btn.danger { color: var(--red); }
.btn.sm { height: 32px; padding: 0 11px; font-size: 14px; }
/* Tombol tampak nonaktif (syarat belum terpenuhi) tapi tetap bisa diklik untuk memunculkan notice. */
.btn.is-off { opacity: 0.45; }

.chip { font-size: 13px; font-weight: 700; padding: 3px 10px; border-radius: 99px; border: 1px solid var(--line-3); color: var(--text-2); white-space: nowrap; }
.chip.ready { color: var(--green); border-color: var(--green); }
.chip.processing, .chip.warn { color: var(--text-2); border-color: var(--text-2); }
.chip.error { color: var(--red); border-color: var(--red); }
.relay-count { font-size: 14px; font-weight: 600; color: var(--text-2); margin-left: 6px; }

.drop { border: 1.5px dashed var(--line-3); border-radius: 12px; padding: 18px 12px; display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer; text-align: center; transition: background 0.12s, border-color 0.12s; color: var(--text); }
.drop span { font-size: 14px; color: var(--muted); }
.drop:hover, .drop.over { background: var(--accent-glow); border-color: var(--accent); }

.bar { height: 5px; border-radius: 99px; background: var(--panel-3); overflow: hidden; }
.bar > div { height: 100%; width: 35%; background: var(--accent); border-radius: 99px; animation: slide 1.1s ease-in-out infinite; }
@keyframes slide { 0% { margin-left: -35%; } 100% { margin-left: 100%; } }

.kv { display: flex; flex-direction: column; gap: 6px; }
.kv > div { display: flex; justify-content: space-between; gap: 10px; font-size: 14px; }
.kv span { color: var(--muted); }
.hint { font-size: 14px; line-height: 1.55; color: var(--text-2); }
.hint b { font-size: inherit; }
.hint.hot { color: var(--text); font-weight: 600; }

/* Jarak trail: angka horizontal headline + profil 3D sekunder dari DEM. Catatan "tidak lengkap"
   memakai amber (peringatan), BUKAN merah (merah = SOS saja). Token fase2: --line, --text-2, --amber. */
.dist { margin-top: 2px; padding: 8px 10px; background: var(--line); border-radius: 9px; display: flex; flex-direction: column; gap: 5px; }
.dist-head { display: flex; align-items: baseline; gap: 8px; }
.dist-head .lbl { flex-shrink: 0; }
.dist-head b { font-size: 15px; color: var(--text); font-variant-numeric: tabular-nums; }
.dist-sub { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; color: var(--text-2); }
.dist-sub .lbl { flex-shrink: 0; }
.dist-sub b { font-size: 14px; font-variant-numeric: tabular-nums; color: var(--text); }
.dist-sub .note { font-size: 13px; color: var(--amber); }
.lnk { margin-left: auto; background: none; border: none; padding: 0; color: var(--text-2); font-size: 13px; text-decoration: underline; cursor: pointer; }
.lnk:hover { color: var(--text); }
.seg { list-style: none; margin: 0; padding: 5px 0 0; display: flex; flex-direction: column; gap: 3px; border-top: 1px solid var(--line-2); }
.seg li { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; color: var(--text-2); font-variant-numeric: tabular-nums; }

.err { font-size: 14px; line-height: 1.5; color: var(--red); background: var(--red-bg); border: 1px solid var(--red-line); border-radius: 9px; padding: 8px 10px; }
.err b { font-size: inherit; color: inherit; }
.err.sm { font-size: 14px; }

.dev { border: 0; border-top: 1px solid var(--line); border-radius: 0; padding: 12px 0; display: flex; flex-direction: column; gap: 8px; background: transparent; }
.dev:first-of-type { border-top: 0; padding-top: 0; }
.dev-top { display: flex; align-items: center; gap: 10px; }
.nid { width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; background: var(--blue-glow); color: var(--blue-fg); font-weight: 700; font-size: 15px; flex-shrink: 0; }
.dev-cfg { font-size: 14px; color: var(--text-2); }
.dev-slot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

@media (max-width: 900px) { .setup { position: fixed; left: var(--edge); width: auto; } }
.adv-open { width: 100%; justify-content: space-between; }
</style>