<template>
  <aside class="setup floating">
    <div class="sh">
      <div class="slbl"><strong>Setup</strong><span>Lokasi, DEM &amp; perangkat</span></div>
      <button class="tbtn" @click="site.showSetup = false; site.editMode = null" title="Tutup">
        <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
      </button>
    </div>

    <div class="stabs">
      <button :class="{ on: tab === 'site' }" @click="tab = 'site'">Lokasi &amp; relay</button>
      <button :class="{ on: tab === 'dev' }" @click="tab = 'dev'">
        Perangkat<i v-if="dev.outOfSync.length" class="dot"></i>
      </button>
    </div>

    <!-- ═════════ TAB LOKASI ═════════ -->
    <div v-if="tab === 'site'" class="sb">
      <p v-if="site.error" class="err">{{ site.error }}</p>

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
            <div class="row" v-if="site.site.trail.length">
              <button class="btn sm" @click="site.undoTrail()">Undo titik</button>
              <button class="btn sm danger" @click="site.clearTrail()">Hapus trail</button>
            </div>
            <p v-if="site.editMode" class="hint hot">
              {{ site.editMode === "base" ? "Klik satu titik di peta untuk menaruh base." : "Klik di peta berurutan dari base ke arah puncak." }}
            </p>
          </div>
        </section>

        <!-- 3. parameter -->
        <section class="pnl">
          <div class="ph"><span class="tl">3 · Parameter relay</span></div>
          <div class="pb grid2">
            <label v-for="f in paramFields" :key="f.k"><span class="lbl">{{ f.label }}<ParamTip>{{ f.tip }}</ParamTip></span>
              <input class="inp" type="number" :step="f.step" v-model.number="site.site.params[f.k]" />
            </label>
            <p class="hint wide"><b>Anggaran daya tautan.</b> Bawaan = angka rencana C-251 (bukan hasil ukur). Isi dari datasheet, lalu <b>kalibrasi dari RSSI lapangan</b> (bagian 5).</p>
            <label v-for="f in budgetFields" :key="f.k"><span class="lbl">{{ f.label }}<ParamTip>{{ f.tip }}</ParamTip></span>
              <input class="inp" type="number" :step="f.step" v-model.number="site.site.params[f.k]" />
            </label>
            <div class="wide canopy">
              <span class="lbl">Vegetasi (opsional)</span>
              <template v-if="site.site.canopy">
                <p class="hint">Raster kanopi dipakai: <b>{{ site.site.canopy.filename || "canopy.tif" }}</b>, {{ site.site.canopy.res_m }} m/piksel,
                  tinggi maks {{ site.site.canopy.max_height_m }} m, {{ site.site.canopy.canopy_pct }}% area bertajuk,
                  menutup {{ site.site.canopy.dem_overlap_pct }}% area DEM.</p>
                <button class="btn sm" :disabled="site.busy" @click="site.removeCanopy()">Hapus data kanopi</button>
              </template>
              <template v-else>
                <p class="hint">Tanpa data kanopi, vegetasi dianggap tidak ada dan hasil di hutan optimistis. Unggah GeoTIFF <b>tinggi kanopi (meter)</b>, mis. dari peta tinggi kanopi global (ETH 10 m atau Meta/WRI 1 m; cek cakupan dan lisensi).</p>
                <input ref="canopyInput" type="file" accept=".tif,.tiff" hidden @change="onCanopy" />
                <button class="btn sm" :disabled="site.busy" @click="canopyInput.click()">Unggah raster kanopi</button>
              </template>
            </div>
            <button class="btn wide" @click="site.saveInputs()">Simpan &amp; hitung ulang</button>
          </div>
        </section>

        <!-- 4. hasil -->
        <section class="pnl">
          <div class="ph"><span class="tl">4 · Hasil penempatan relay</span>
            <span v-if="plan" class="chip" :class="plan.covers_all ? 'ready' : 'error'">
              {{ plan.covers_all ? "trail tercover" : `${plan.uncovered_points} titik belum tercover` }}
            </span>
            <span v-if="plan?.manual" class="chip" style="margin-left:4px">posisi manual</span>
          </div>
          <div class="pb">
            <button class="btn primary" :disabled="site.busy || !site.site.base || site.site.trail.length < 1" @click="site.runPlan()">
              {{ site.busy ? "Menghitung…" : plan ? "Hitung ulang" : "Hitung relay" }}
            </button>
            <p v-if="!plan" class="hint">Dihitung otomatis begitu base + minimal 2 titik trail ada.</p>
            <template v-else>
              <p class="hint">Elevasi base {{ plan.base_elev_m }} m.<template v-if="plan.trail_km != null"> Jalur {{ plan.trail_km }} km, tercover {{ plan.covered_km }} km<template v-if="plan.coverage_pct != null"> ({{ plan.coverage_pct }}% sampel terjangkau)</template>.</template>
                <b>Redaman</b> = medan (difraksi) + vegetasi, dalam dB. <b>Margin</b> = RSSI prediksi di atas sensitivitas; hijau bila ≥ {{ site.site?.params?.fade_margin_db ?? 10 }} dB (margin fading yang disyaratkan). Redaman medan maksimum yang dipercaya model: {{ site.site?.params?.max_loss_db ?? 6 }} dB.</p>
              <p v-if="plan.uses_clutter && plan.clutter_cover_pct != null && plan.clutter_cover_pct < 99.5" class="err">Data kanopi hanya menutup {{ plan.clutter_cover_pct }}% jalur; sisanya dianggap tanpa vegetasi.</p>
              <p v-else-if="plan.uses_clutter === false" class="hint warnbox">Tanpa data vegetasi: hasil optimistis di area berhutan. Unggah raster tinggi kanopi di bagian 3.</p>
              <p v-if="plan.relays.length" class="hint">Geser penanda R di peta (selama panel Setup terbuka) sesuai kondisi lapangan; redaman tiap link dihitung ulang dari DEM. "Hitung ulang" = kembali ke rekomendasi otomatis.</p>
              <table class="tbl" v-if="plan.relays.length">
                <thead><tr><th>#</th><th>Posisi</th><th>Hop</th><th>Redaman</th><th>Margin</th></tr></thead>
                <tbody>
                  <tr v-for="r in plan.relays" :key="r.n">
                    <td>R{{ r.n }}</td>
                    <td :title="`elevasi ${r.elev_m} m`">{{ r.lat.toFixed(5) }}, {{ r.lon.toFixed(5) }}</td>
                    <td :title="`terhubung ke ${r.parent ? 'R' + r.parent : 'base'}`">{{ r.hop_km }} km</td>
                    <td v-if="r.loss_db != null" :class="r.link_ok === false ? 'warn' : 'ok'"
                        :title="`medan ${r.loss_db} dB + vegetasi ${r.veg_db ?? 0} dB`">{{ (r.loss_db + (r.veg_db ?? 0)).toFixed(1) }} dB</td>
                    <td v-else :class="r.margin_m < 3 ? 'warn' : 'ok'" title="rencana lama: margin Fresnel; tekan Hitung ulang">{{ r.margin_m }} m</td>
                    <td v-if="r.fade_margin_db != null" :class="marginClass(r)" :title="`RSSI prediksi ${r.rssi_dbm} dBm`">{{ r.fade_margin_db }} dB</td>
                    <td v-else>—</td>
                  </tr>
                </tbody>
              </table>
              <p v-else-if="plan.covers_all" class="hint">Base langsung menjangkau seluruh trail — tidak perlu relay.</p>
              <p v-if="plan.message" class="err">{{ plan.message }}</p>
              <a class="btn" :href="planGpxUrl" download>Unduh GPX rencana</a>
            </template>
          </div>
        </section>

        <!-- 5. kalibrasi dari RSSI lapangan -->
        <section class="pnl">
          <div class="ph"><span class="tl">5 · Kalibrasi RSSI lapangan</span></div>
          <div class="pb">
            <p class="hint">Membandingkan RSSI <b>terukur</b> (paket langsung 0 hop, GPS valid, 72 jam terakhir) dengan RSSI <b>prediksi</b> model di posisi yang sama,
              lalu menyarankan <b>offset kalibrasi</b> dan <b>margin fading</b>. <b>Hanya pakai data lapangan</b>, jangan data sintetis. Kalibrasi pada jarak di mana
              PDR masih tinggi: paket yang hilang di tepi jangkauan tidak punya RSSI sehingga hasil terlihat terlalu bagus.</p>
            <label><span class="lbl">Batas jarak (km, opsional)</span>
              <input class="inp" type="number" step="0.1" v-model.number="calMaxKm" placeholder="semua" />
            </label>
            <button class="btn" :disabled="site.calibrating || !site.site.base" @click="site.calibrate({ maxKm: calMaxKm || null })">
              {{ site.calibrating ? "Menghitung…" : "Hitung dari data lapangan" }}
            </button>
            <template v-if="site.calibration">
              <p v-for="m in site.calibration.problems" :key="m" class="err">{{ m }}</p>
              <table v-if="site.calibration.n" class="tbl">
                <tbody>
                  <tr><td>Paket dipakai</td><td>{{ site.calibration.n }} <template v-if="site.calibration.n_outside_dem">({{ site.calibration.n_outside_dem }} di luar DEM dibuang)</template></td></tr>
                  <tr><td>Jarak P10–P90</td><td>{{ site.calibration.dist_p10_km }}–{{ site.calibration.dist_p90_km }} km</td></tr>
                  <tr><td>Bias (terukur − prediksi)</td><td>{{ site.calibration.bias_median_db }} dB</td></tr>
                  <tr><td>Sigma residu</td><td>{{ site.calibration.sigma_db ?? "—" }} dB</td></tr>
                  <tr><td>RSSI terendah yang diterima (P1)</td><td>{{ site.calibration.rssi_p01_dbm }} dBm <span class="hint">(sensitivitas efektif tak mungkin lebih baik; sekarang {{ site.calibration.current_sensitivity_dbm }})</span></td></tr>
                  <tr><td>Saran offset kalibrasi</td><td><b>{{ site.calibration.suggested_calib_offset_db }} dB</b> (sekarang {{ site.calibration.current_offset_db }})</td></tr>
                  <tr><td>Saran margin fading</td><td><b>{{ site.calibration.suggested_fade_margin_db ?? "—" }} dB</b> (sekarang {{ site.calibration.current_fade_margin_db }})</td></tr>
                </tbody>
              </table>
              <button class="btn primary" :disabled="!site.calibration.reliable || site.busy" @click="site.applyCalibration()">Terapkan saran &amp; hitung ulang</button>
              <p v-if="site.calibration.n && !site.calibration.reliable" class="hint">Belum bisa diterapkan: data belum cukup andal (lihat catatan di atas).</p>
            </template>
          </div>
        </section>
      </template>
    </div>

    <!-- ═════════ TAB PERANGKAT ═════════ -->
    <div v-else class="sb">
      <p v-if="dev.error" class="err">{{ dev.error }}</p>

      <section class="pnl">
        <div class="ph"><span class="tl">Daftar perangkat</span>
          <button class="btn sm" :disabled="!dev.outOfSync.length || dev.busy" @click="dev.pushAll()">
            Push semua ({{ dev.outOfSync.length }})
          </button>
        </div>
        <div class="pb">
          <p v-if="!dev.devices.length" class="hint">Belum ada perangkat. Tambahkan di bawah.</p>
          <div v-for="d in dev.devices" :key="d.id" class="dev">
            <div class="dev-top">
              <span class="nid">{{ d.node_id }}</span>
              <div class="grow"><b>{{ d.name }}</b><span class="lbl">{{ d.role }}<template v-if="d.hiker_code"> · {{ d.hiker_code }}</template></span></div>
              <span class="chip" :class="syncClass(d)">{{ syncLabel(d) }}</span>
            </div>
            <div class="dev-cfg">
              lapor {{ d.config.report_interval_s }} dtk · TX {{ d.config.tx_power_dbm }} dBm · SF{{ d.config.sf }}
            </div>
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
              <button class="btn sm primary" :disabled="dev.busy || pushing(d)" @click="dev.push(d.id)">
                {{ pushing(d) ? "Menunggu bridge…" : "Push ke alat" }}
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
          <label><span class="lbl">Interval lapor (dtk)<ParamTip>Selang node mengirim posisi. MISMATCH: firmware _optimized mengirim kontinu (jeda minimum 300 ms), _real tiap 5000 ms; angka '30 dtk' TIDAK ada di firmware. Lagipula downlink konfigurasi belum dimengerti firmware, jadi nilai ini BELUM sampai ke alat.</ParamTip></span><input class="inp" type="number" v-model.number="form.config.report_interval_s" /></label>
          <label><span class="lbl">TX power (dBm)<ParamTip>Daya pancar node. MISMATCH: alat memakai POWER_22 = 22 dBm hardcoded; batas form ini (2–20) bahkan tak bisa mencapai 22. Downlink konfigurasi belum jalan, jadi nilai ini BELUM mengubah alat.</ParamTip></span><input class="inp" type="number" v-model.number="form.config.tx_power_dbm" /></label>
          <label><span class="lbl">Spreading factor<ParamTip>Tukar jangkauan vs kecepatan. MISMATCH: firmware menyetel AIR_DATA_RATE_010_24 (2,4 kbps E220), bukan angka SF numerik; padanan 'SF9 = 2,4 kbps' adalah ASUMSI, bukan fakta datasheet. Nilai sf ini saat ini hanya katalog dashboard.</ParamTip></span><input class="inp" type="number" min="5" max="11" v-model.number="form.config.sf" /></label>
          <div class="row wide">
            <button class="btn primary grow" :disabled="dev.busy || !form.name || !form.node_id" @click="submit">
              {{ editId ? "Simpan perubahan" : "Tambah" }}
            </button>
            <button v-if="editId" class="btn" @click="resetForm">Batal</button>
          </div>
          <p class="hint wide">
            Menyimpan hanya mengubah data di dashboard. <b>Push</b> memasukkan perintah ke antrean; bridge serial di PC base
            yang mengirimnya ke alat dan mengonfirmasi balik. Tanpa bridge yang jalan, status tertahan di “menunggu bridge”.
          </p>
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useSiteStore } from "../stores/site";
import { useDeviceStore } from "../stores/devices";
import { planGpxUrl } from "../services/api";
import { trailSegments } from "../utils/routeGeo";
import ParamTip from "./ParamTip.vue";

const site = useSiteStore();
const dev = useDeviceStore();
const tab = ref("site");

// ── lokasi ──
const canopyInput = ref(null);
const calMaxKm = ref(null);
async function onCanopy(e) {
  const f = e.target.files[0];
  e.target.value = "";
  if (f) await site.uploadCanopyFile(f);
}
const fileInput = ref(null);
const picked = ref(null);
const siteName = ref("");
const dragOver = ref(false);
const plan = computed(() => site.site?.plan);

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

const statusLabel = computed(
  () => ({ processing: "memproses", ready: "siap", error: "gagal" }[site.site?.status] || site.site?.status)
);
const budgetFields = [
  { k: "tx_dbm", label: "Daya TX (dBm)", step: 1,
    tip: "Daya pancar yang DIASUMSIKAN model. MISMATCH: alat nyata memakai POWER_22 = 22 dBm (hardcoded di firmware semua peran/varian); model default 21 dBm. Nilai ini hanya memengaruhi hitungan planner, bukan alat." },
  { k: "sensitivity_dbm", label: "Sensitivitas (dBm)", step: 1,
    tip: "RSSI terlemah yang masih bisa didecode. Makin negatif = makin peka = jangkauan naik. C-251: SF9 ~ -137 dBm, SF11 ~ -148 dBm; cek datasheet E220 untuk angka pasti." },
  { k: "gain_hiker_dbi", label: "Gain antena pendaki (dBi)", step: 0.5,
    tip: "Penguatan antena pendaki. Naik = jangkauan naik. Isi dari spesifikasi antena fisik." },
  { k: "gain_relay_dbi", label: "Gain antena relay/base (dBi)", step: 0.5,
    tip: "Penguatan antena relay/base. Isi dari spesifikasi antena fisik." },
  { k: "fade_margin_db", label: "Margin fading (dB)", step: 0.5,
    tip: "Cadangan daya di atas sensitivitas untuk melawan fading. Naik = rencana lebih aman tapi jangkauan efektif turun. Praktik rekayasa; setel dari sebaran shadowing lapangan." },
  { k: "veg_scale", label: "Skala vegetasi (0–1)", step: 0.1,
    tip: "Pengali redaman vegetasi di model. Terkait data kanopi, bukan alat." },
  { k: "calib_offset_db", label: "Offset kalibrasi (dB)", step: 0.5,
    tip: "Redaman tambahan hasil kalibrasi RSSI lapangan. Dari proses kalibrasi, bukan datasheet." },
];
// warna margin fading: merah = link putus, abu = di bawah margin yang disyaratkan, hijau = cukup
function marginClass(r) {
  if (r.link_ok === false) return "warn";
  return r.fade_margin_db < (site.site?.params?.fade_margin_db ?? 10) ? "warn" : "ok";
}
const paramFields = [
  { k: "freq_mhz", label: "Frekuensi (MHz)", step: 1,
    tip: "Frekuensi kerja yang dipakai MODEL planner (menggeser FSPL/Fresnel/redaman vegetasi). Naik = rugi lintasan lebih besar (jangkauan model turun). Pita legal Indonesia 920–923 MHz (C-251, Permenkominfo 1/2019); default 922. Firmware memakai LORA_CHANNEL 70 — frekuensi MHz aktualnya tercetak di Serial saat boot (config.h:18), belum terkonfirmasi sama persis dengan nilai ini; channel 70 pada E220 kemungkinan ~920 MHz tapi ini ASUMSI dari rumus umum, bukan fakta terukur. Semua node WAJIB di kanal yang sama atau tak saling dengar." },
  { k: "antenna_h_m", label: "Antena pendaki (m)", step: 0.5,
    tip: "Tinggi antena node pendaki di atas tanah. Naik = garis pandang lebih baik, jangkauan naik. Samakan dengan tinggi pasang fisik di lapangan." },
  { k: "relay_h_m", label: "Antena relay (m)", step: 0.5,
    tip: "Tinggi antena relay/base. Naik = jangkauan naik. Isi dengan tinggi tiang fisik sebenarnya." },
  { k: "max_hop_km", label: "Hop maks (km)", step: 0.1,
    tip: "Jarak satu lompatan yang dianggap mungkin oleh planner. Terlalu besar = rencana optimistis. Acuan C-251: LOS >= 1 km, NLOS >= 300 m — setel realistis terhadap jangkauan alat." },
  { k: "max_loss_db", label: "Redaman medan maks (dB)", step: 0.5,
    tip: "Ambang kepercayaan model difraksi (batas MODEL, bukan anggaran daya). Di atas ini link dianggap tak layak. Batas model, bukan batas alat." },
  { k: "dem_error_m", label: "Cadangan galat DEM (m)", step: 0.5,
    tip: "Medan dianggap setinggi ini lebih tinggi (cadangan galat DEM). Naik = rencana lebih konservatif. Terkait kualitas DEM, bukan alat." },
  { k: "max_relays", label: "Relay maks", step: 1,
    tip: "Batas jumlah relay yang dicari planner. Isi sesuai jumlah relay fisik yang tersedia." },
  { k: "search_radius_km", label: "Radius cari (km)", step: 0.05,
    tip: "Sejauh apa kandidat relay dicari dari jalur. Naik = lebih banyak kandidat, hitungan lebih lama." },
  { k: "search_step_km", label: "Langkah cari (km)", step: 0.01,
    tip: "Kerapatan grid kandidat relay. Makin kecil = makin teliti tapi lebih lambat." },
];

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
const emptyForm = () => ({ node_id: null, name: "", role: "tracker", config: { report_interval_s: 30, tx_power_dbm: 17, sf: 9 } });
const form = reactive(emptyForm());
const editId = ref(null);

function resetForm() {
  Object.assign(form, emptyForm());
  editId.value = null;
}
function edit(d) {
  editId.value = d.id;
  Object.assign(form, { node_id: d.node_id, name: d.name, role: d.role, config: { ...d.config } });
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
.btn.active { background: var(--btn); border-color: var(--btn); color: var(--on-btn); }
.btn.danger { color: var(--red); }
.btn.sm { height: 32px; padding: 0 11px; font-size: 14px; }

.chip { font-size: 13px; font-weight: 700; padding: 3px 10px; border-radius: 99px; border: 1px solid var(--line-3); color: var(--text-2); white-space: nowrap; }
.chip.ready { color: var(--green); border-color: var(--green); }
.chip.processing, .chip.warn { color: var(--text-2); border-color: var(--text-2); }
.chip.error { color: var(--red); border-color: var(--red); }

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

.tbl { width: 100%; border-collapse: collapse; font-size: 14px; color: var(--text); }
.tbl th { text-align: left; font-size: 13px; font-weight: 700; color: var(--text-2); padding: 5px 6px; border-bottom: 1px solid var(--line-3); }
.tbl td { padding: 7px 6px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; color: var(--text); }
.tbl td b { font-size: inherit; }
.tbl .ok { color: var(--green); font-weight: 700; }
.tbl .warn { color: var(--text-2); font-weight: 700; }

.dev { border: 0; border-top: 1px solid var(--line); border-radius: 0; padding: 12px 0; display: flex; flex-direction: column; gap: 8px; background: transparent; }
.dev:first-of-type { border-top: 0; padding-top: 0; }
.dev-top { display: flex; align-items: center; gap: 10px; }
.nid { width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; background: var(--blue-glow); color: var(--blue-fg); font-weight: 700; font-size: 15px; flex-shrink: 0; }
.dev-cfg { font-size: 14px; color: var(--text-2); }
.dev-slot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

@media (max-width: 900px) { .setup { position: fixed; left: var(--edge); width: auto; } }
.canopy { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.warnbox { color: var(--text); font-weight: 600; }
</style>