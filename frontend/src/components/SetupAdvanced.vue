<template>
  <div class="sb">
    <div class="advbar">
      <button class="btn sm" type="button" @click="$emit('back')">&larr; Kembali</button>
      <strong>Konfigurasi Lanjutan</strong>
    </div>

    <p v-if="site.error" class="err adv-err">{{ site.error }}</p>

    <p v-if="!site.ready" class="hint adv-pad">Unggah DEM dulu di langkah 1.</p>

    <template v-else>
      <!-- 3. parameter -->
      <section class="pnl">
        <div class="ph"><span class="tl">3 · Parameter relay</span></div>
        <div class="pb grid2">
          <label v-for="f in paramFields" :key="f.k"><span class="lbl">{{ f.label }}</span>
            <input class="inp" type="number" :step="f.step" v-model.number="site.site.params[f.k]" />
          </label>
          <label v-for="f in budgetFields" :key="f.k"><span class="lbl">{{ f.label }}</span>
            <input class="inp" type="number" :step="f.step" v-model.number="site.site.params[f.k]" />
          </label>
          <div class="wide canopy">
            <span class="lbl">Vegetasi (opsional)</span>
            <template v-if="site.site.canopy">
              <span class="val">{{ site.site.canopy.filename || "canopy.tif" }}</span>
              <button class="btn sm" :disabled="site.busy" @click="site.removeCanopy()">Hapus data kanopi</button>
            </template>
            <template v-else>
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
          <template v-if="plan">
            <p v-if="plan.trail_km != null" class="hint">
              Jalur {{ plan.trail_km }} km · tercover {{ plan.covered_km }} km<template v-if="plan.coverage_pct != null"> ({{ plan.coverage_pct }}%)</template>
            </p>
            <p v-if="plan.uses_clutter && plan.clutter_cover_pct != null && plan.clutter_cover_pct < 99.5" class="err">Data kanopi hanya menutup {{ plan.clutter_cover_pct }}% jalur.</p>
            <p v-else-if="plan.uses_clutter === false" class="hint warnbox">Tanpa data vegetasi.</p>
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
            <p v-else-if="plan.covers_all" class="hint">Tanpa relay: base menjangkau seluruh trail.</p>
            <p v-if="plan.message" class="err">{{ plan.message }}</p>
            <a class="btn" :href="planGpxUrl" download>Unduh GPX rencana</a>
          </template>
        </div>
      </section>

      <!-- 5. kalibrasi dari RSSI lapangan -->
      <section class="pnl">
        <div class="ph"><span class="tl">5 · Kalibrasi RSSI lapangan</span></div>
        <div class="pb">
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
                <tr><td>Paket dipakai</td><td>{{ site.calibration.n }}<template v-if="site.calibration.n_outside_dem"> ({{ site.calibration.n_outside_dem }} di luar DEM)</template></td></tr>
                <tr><td>Jarak P10–P90</td><td>{{ site.calibration.dist_p10_km }}–{{ site.calibration.dist_p90_km }} km</td></tr>
                <tr><td>Bias (terukur − prediksi)</td><td>{{ site.calibration.bias_median_db }} dB</td></tr>
                <tr><td>Sigma residu</td><td>{{ site.calibration.sigma_db ?? "—" }} dB</td></tr>
                <tr><td>RSSI terendah (P1)</td><td>{{ site.calibration.rssi_p01_dbm }} dBm</td></tr>
                <tr><td>Saran offset kalibrasi</td><td><b>{{ site.calibration.suggested_calib_offset_db }} dB</b> (sekarang {{ site.calibration.current_offset_db }})</td></tr>
                <tr><td>Saran margin fading</td><td><b>{{ site.calibration.suggested_fade_margin_db ?? "—" }} dB</b> (sekarang {{ site.calibration.current_fade_margin_db }})</td></tr>
              </tbody>
            </table>
            <button class="btn primary" :disabled="!site.calibration.reliable || site.busy" @click="site.applyCalibration()">Terapkan saran &amp; hitung ulang</button>
            <p v-if="site.calibration.n && !site.calibration.reliable" class="hint">Data belum cukup andal untuk diterapkan.</p>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
// Langkah 3, 4, 5 Setup (dipindah dari SetupPanel.vue). Logic/aksi store TIDAK diubah, hanya penempatan UI
// dan teks penjelasan yang dipangkas supaya ringkas untuk operator awam.
import { computed, ref } from "vue";
import { useSiteStore } from "../stores/site";
import { planGpxUrl } from "../services/api";

defineEmits(["back"]);

const site = useSiteStore();
const canopyInput = ref(null);
const calMaxKm = ref(null);
const plan = computed(() => site.site?.plan);

async function onCanopy(e) {
  const f = e.target.files[0];
  e.target.value = "";
  if (f) await site.uploadCanopyFile(f);
}

// warna margin fading: merah = link putus, abu = di bawah margin yang disyaratkan, hijau = cukup
function marginClass(r) {
  if (r.link_ok === false) return "warn";
  return r.fade_margin_db < (site.site?.params?.fade_margin_db ?? 10) ? "warn" : "ok";
}

// Hanya label + step. Penjelasan panjang (tooltip) sengaja dihapus.
const paramFields = [
  { k: "freq_mhz", label: "Frekuensi (MHz)", step: 1 },
  { k: "antenna_h_m", label: "Antena pendaki (m)", step: 0.5 },
  { k: "relay_h_m", label: "Antena relay (m)", step: 0.5 },
  { k: "max_hop_km", label: "Hop maks (km)", step: 0.1 },
  { k: "max_loss_db", label: "Redaman medan maks (dB)", step: 0.5 },
  { k: "dem_error_m", label: "Cadangan galat DEM (m)", step: 0.5 },
  { k: "max_relays", label: "Relay maks", step: 1 },
  { k: "search_radius_km", label: "Radius cari (km)", step: 0.05 },
  { k: "search_step_km", label: "Langkah cari (km)", step: 0.01 },
];
// Margin fading & offset kalibrasi SENGAJA tidak ditampilkan sebagai input operator (membingungkan).
// Backend tetap memakai default (fade_margin_db=10, calib_offset_db=0) atau nilai dari fitur Kalibrasi
// RSSI lapangan (bagian 5) yang masih menyetelnya otomatis di belakang layar.
const budgetFields = [
  { k: "tx_dbm", label: "Daya TX (dBm)", step: 1 },
  { k: "sensitivity_dbm", label: "Sensitivitas (dBm)", step: 1 },
  { k: "gain_hiker_dbi", label: "Gain antena pendaki (dBi)", step: 0.5 },
  { k: "gain_relay_dbi", label: "Gain antena relay/base (dBi)", step: 0.5 },
  { k: "veg_scale", label: "Skala vegetasi (0–1)", step: 0.1 },
];
</script>

<style scoped>
.advbar { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 2; background: var(--panel); }
.advbar strong { font-family: var(--font-head); font-size: 15px; font-weight: 700; color: var(--text); }
.adv-err { margin: 12px 14px 0; }
.adv-pad { padding: 14px; }

.pb { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 10px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.grid2 .wide, .wide { grid-column: 1 / -1; }
.lbl { font-size: 14px; color: var(--text-2); font-weight: 600; }
.val { font-size: 14px; color: var(--text); word-break: break-all; }
b { font-size: 15px; font-weight: 600; color: var(--text); }
label { display: flex; flex-direction: column; gap: 5px; }

.inp { width: 100%; height: 38px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--text); padding: 0 10px; font: 14px var(--font); outline: none; }
.inp:focus { border-color: var(--accent); }

.btn { height: 38px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--line-3); background: var(--panel-3); color: var(--text); font: 600 14px var(--font); cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
.btn:hover:not(:disabled) { border-color: var(--accent); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--btn); border-color: var(--btn); color: var(--on-btn); }
.btn.primary:hover:not(:disabled) { background: var(--btn-hover); border-color: var(--btn-hover); }
.btn.sm { height: 32px; padding: 0 11px; font-size: 14px; }

.chip { font-size: 13px; font-weight: 700; padding: 3px 10px; border-radius: 99px; border: 1px solid var(--line-3); color: var(--text-2); white-space: nowrap; }
.chip.ready { color: var(--green); border-color: var(--green); }
.chip.error { color: var(--red); border-color: var(--red); }

.hint { font-size: 14px; line-height: 1.55; color: var(--text-2); }
.warnbox { color: var(--text); font-weight: 600; }
.err { font-size: 14px; line-height: 1.5; color: var(--red); background: var(--red-bg); border: 1px solid var(--red-line); border-radius: 9px; padding: 8px 10px; }

.tbl { width: 100%; border-collapse: collapse; font-size: 14px; color: var(--text); }
.tbl th { text-align: left; font-size: 13px; font-weight: 700; color: var(--text-2); padding: 5px 6px; border-bottom: 1px solid var(--line-3); }
.tbl td { padding: 7px 6px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; color: var(--text); }
.tbl td b { font-size: inherit; }
.tbl .ok { color: var(--green); font-weight: 700; }
.tbl .warn { color: var(--text-2); font-weight: 700; }

.canopy { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
</style>