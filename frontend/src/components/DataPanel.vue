<template>
  <div class="pnl">
    <div class="ph"><div class="tl"><svg class="ic" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></svg>Data &amp; cadangan</div></div>
    <div class="pb dp">
      <div class="dp-sec">
        <div class="dp-t">Ekspor CSV</div>
        <p class="dp-h">Semua paket dari semua sesi (untuk laporan, analisis kekuatan sinyal dan paket yang sampai). Kosongkan tanggal untuk mengunduh semuanya. CSV per sesi ada di tombol <b>Unduh CSV</b> pada daftar sesi.</p>
        <label class="dp-f"><span>Dari</span><input type="datetime-local" v-model="from" /></label>
        <label class="dp-f"><span>Sampai</span><input type="datetime-local" v-model="to" /></label>
        <a class="dp-btn" :href="csvHref" download>Unduh CSV</a>
      </div>

      <div class="dp-sec">
        <div class="dp-t">Cadangkan data</div>
        <p class="dp-h">Satu berkas ZIP berisi CSV pendaki, sesi, alarm, seluruh paket posisi, dan log mentah serial. Ini cadangan <b>data operasional</b>, bukan salinan penuh basis data (peta DEM dan rencana relay tidak ikut).</p>
        <a class="dp-btn" :href="backupZipUrl" download>Cadangkan data (ZIP)</a>
        <p class="dp-h">Memulihkan data dilakukan manual agar tidak menimpa data tanpa sengaja — lihat bagian “Cadangan &amp; pemulihan” di README.</p>
      </div>

      <div class="dp-sec">
        <div class="dp-t">Folder data</div>
        <p class="dp-h" v-if="info">Lokasi: <code>{{ info.data_dir }}</code> (log mentah serial ada di subfolder <code>raw</code>).</p>
        <p class="dp-h" v-else>Info folder belum bisa dimuat.</p>
        <div class="dp-row">
          <button v-if="info?.can_open" class="dp-btn" type="button" @click="openFolder">Buka folder data</button>
          <button v-else-if="info" class="dp-btn" type="button" @click="copyPath">{{ copied ? "Tersalin ✓" : "Salin lokasi folder" }}</button>
        </div>
        <div v-if="msg" class="dp-msg" role="status">{{ msg }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { backupZipUrl, fetchDataInfo, openDataFolder, rangeCsvUrl } from "../services/api";

const from = ref("");
const to = ref("");
const info = ref(null);
const msg = ref("");
const copied = ref(false);

// input datetime-local = jam lokal browser tanpa zona; diubah ke ISO UTC supaya backend tidak salah tafsir
const iso = (v) => (v ? new Date(v).toISOString() : "");
const csvHref = computed(() => {
  try {
    return rangeCsvUrl(iso(from.value), iso(to.value));
  } catch (e) {
    return rangeCsvUrl("", "");
  }
});

onMounted(async () => {
  try {
    info.value = await fetchDataInfo();
  } catch (e) {
    /* backend lama tanpa endpoint ini: bagian folder disembunyikan */
  }
});

async function openFolder() {
  msg.value = "";
  try {
    await openDataFolder();
  } catch (e) {
    msg.value = e.message;
  }
}
async function copyPath() {
  try {
    await navigator.clipboard.writeText(info.value.data_dir);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
  } catch (e) {
    msg.value = `Salin manual: ${info.value.data_dir}`;
  }
}
</script>

<style scoped>
.dp { display: flex; flex-direction: column; gap: 0; }
.dp-sec { display: flex; flex-direction: column; gap: 8px; border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 12px 0; }
.dp-sec:first-child { border-top: 0; padding-top: 0; }
.dp-t { font-size: 13px; font-weight: 700; color: var(--text); }
.dp-h { font-size: 12.5px; color: var(--text-2); line-height: 1.5; }
.dp-h code { font-size: 12px; word-break: break-all; }
.dp-f { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-2); }
.dp-f span { width: 52px; }
.dp-f input { flex: 1; min-height: 34px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-2); color: var(--text); padding: 0 8px; font-family: inherit; font-size: 13px; }
.dp-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 34px; padding: 4px 12px; border-radius: 8px; border: 1px solid var(--blue-fg); background: transparent; color: var(--blue-fg); font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; font-family: inherit; }
.dp-btn:hover { background: var(--btn); border-color: var(--btn); color: var(--on-btn); }
.dp-row { display: flex; gap: 8px; }
.dp-msg { font-size: 12.5px; color: var(--text-2); }
</style>