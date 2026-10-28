<template>
  <div class="pnl">
    <div class="ph ph-toggle" @click="toggle" role="button" tabindex="0" :aria-expanded="open" title="Buka/tutup panel sesi" @keydown.enter.prevent="toggle" @keydown.space.prevent="toggle">
      <div class="tl">
        <svg class="ic" viewBox="0 0 24 24"><path d="M3 20l6-11 4 6 3-4 5 9z" /></svg>
        Sesi pendakian
        <span v-if="store.unregistered.length" class="bdg warn" style="margin-left: 6px">{{ store.unregistered.length }} belum check-in</span>
      </div>
      <div class="sv"><svg class="chev" :class="{ open }" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" /></svg>{{ store.active.length }} aktif</div>
    </div>
    <div class="pb">
      <!-- banner: alat kirim data tapi belum di-check-in. Sengaja di luar bagian yang bisa dilipat:
           peringatan keselamatan tidak boleh ikut tersembunyi. -->
      <div v-if="store.unregistered.length" class="sess-warn">
        <strong>Belum check-in:</strong>
        <span v-for="s in store.unregistered" :key="s.id">
          {{ s.hiker_code }}
          <button class="lnk-btn" @click="fillFor(s.hiker_code)">isi data</button>
        </span>
      </div>

      <div v-show="open">
      <!-- daftar sesi aktif / riwayat -->
      <div class="sess-tabs">
        <button :class="{ on: !showHistory }" @click="showHistory = false">Aktif</button>
        <button :class="{ on: showHistory }" @click="openHistory">Riwayat</button>
      </div>

      <div v-if="!list.length" class="empty">{{ showHistory ? "Belum ada riwayat." : "Belum ada pendaki yang check-in." }}</div>
      <div v-else class="sess-list">
        <div v-for="s in list" :key="s.id" class="sess">
          <div class="sess-top">
            <span class="sess-ic" :class="{ warn: s.auto_opened }" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg></span>
            <strong>{{ s.full_name || "Belum check-in" }}</strong>
            <span class="bdg" :class="s.auto_opened ? 'warn' : 'ok'">{{ s.hiker_code }}</span>
          </div>
          <div class="emeta">
            <template v-if="s.trail_name">{{ s.trail_name }} · </template>
            mulai {{ fmt(s.checked_in_at) }}
            <template v-if="s.checked_out_at"> · selesai {{ fmt(s.checked_out_at) }}</template>
            <template v-else> · terakhir terlihat {{ s.last_seen ? fmt(s.last_seen) : "belum ada data" }}</template>
          </div>
          <div v-if="s.emergency_contact" class="emeta">Kontak darurat: {{ s.emergency_contact }}</div>
          <div class="sess-act">
            <a class="mini" :href="sessionGpxUrl(s.id)" download>Unduh GPX</a>
            <a class="mini" :href="sessionCsvUrl(s.id)" download title="Semua paket sesi ini (Excel/CSV): untuk laporan dan analisis sinyal">Unduh CSV</a>
            <button v-if="s.status === 'active'" class="mini warn" @click="doCheckOut(s)">Check-out</button>
          </div>
        </div>
      </div>

      <!-- form check-in -->
      <form class="sess-form" @submit.prevent="submit">
        <div class="sess-ft">Check-in pendaki</div>
        <!-- Pilih alat dari daftar perangkat terdaftar (anti salah ketik). Operator cukup memilih, tidak mengetik kode. -->
        <p v-if="!availableDevices.length" class="sess-hint">Belum ada alat terdaftar - tambahkan di Setup &gt; Perangkat.</p>
        <select v-else v-model="form.hiker_code" required>
          <option value="" disabled>Pilih alat...</option>
          <option v-for="d in availableDevices" :key="d.hiker_code" :value="d.hiker_code">{{ d.hiker_code }} - {{ d.name }}</option>
        </select>
        <input v-model="form.full_name" placeholder="Nama pendaki" required />
        <input v-model="form.emergency_contact" placeholder="Kontak darurat (opsional)" />
        <input v-model="form.trail_name" placeholder="Jalur (opsional)" />
        <div v-if="error" class="sess-err">{{ error }}</div>
        <button class="ack-btn" style="width: 100%" :disabled="busy || !availableDevices.length">{{ busy ? "..." : "Mulai sesi" }}</button>
      </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { sessionCsvUrl, sessionGpxUrl } from "../services/api";
import { useSessionStore } from "../stores/sessions";
import { useDeviceStore } from "../stores/devices";

const store = useSessionStore();
const deviceStore = useDeviceStore();
const open = ref(localStorage.getItem("silacak.sessOpen") !== "0"); // default terbuka: check-in adalah tugas harian operator
function toggle() {
  open.value = !open.value;
  localStorage.setItem("silacak.sessOpen", open.value ? "1" : "0");
}
const showHistory = ref(false);
const busy = ref(false);
const error = ref("");
const form = reactive({ hiker_code: "", full_name: "", emergency_contact: "", trail_name: "" });

const list = computed(() => (showHistory.value ? store.history : store.active));
// Alat yang bisa dipilih untuk check-in: perangkat terdaftar role 'tracker' (punya hiker_code),
// kecuali yang sedang dipakai pendaki terdaftar (sesi aktif non auto_opened). Anti salah ketik.
const availableDevices = computed(() => {
  const busyCodes = new Set(store.active.filter((s) => !s.auto_opened).map((s) => s.hiker_code));
  return deviceStore.devices.filter((d) => d.role === "tracker" && d.hiker_code && !busyCodes.has(d.hiker_code));
});

onMounted(() => {
  // refresh() = muat sekali tanpa polling; daftar alat jarang berubah saat operator check-in.
  deviceStore.refresh();
});

function fmt(iso) {
  return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function fillFor(code) {
  open.value = true;
  form.hiker_code = code;
  // kode alat sudah terisi dari banner "belum check-in"; fokuskan ke "Nama pendaki" (input teks pertama).
  document.querySelector(".sess-form input")?.focus();
}
async function openHistory() {
  showHistory.value = true;
  try {
    await store.loadHistory();
  } catch (e) {
    error.value = e.message;
  }
}
async function submit() {
  error.value = "";
  busy.value = true;
  try {
    await store.checkIn({ ...form });
    form.hiker_code = form.full_name = form.emergency_contact = form.trail_name = "";
    showHistory.value = false;
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function doCheckOut(s) {
  if (!confirm(`Check-out ${s.full_name || s.hiker_code}? Alarm yang masih aktif ikut diselesaikan dan alat hilang dari peta.`)) return;
  error.value = "";
  try {
    await store.checkOut(s.id);
  } catch (e) {
    error.value = e.message;
  }
}
</script>

<style scoped>
.ph-toggle { cursor: pointer; user-select: none; }
.ph-toggle:hover .tl { color: var(--text-2); }
.ph-toggle .sv { display: inline-flex; align-items: center; gap: 4px; }
.chev { width: 10px; height: 10px; fill: none; stroke: currentColor; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; transition: transform 0.15s; }
.chev.open { transform: rotate(90deg); }
/* "belum check-in" = peringatan perlu tindakan, bukan bahaya SOS -> amber (bukan merah). */
.sess-warn { border: 1px solid var(--amber); background: var(--amber-glow); border-radius: 10px; padding: 8px 10px; font-size: 13px; margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; }
.lnk-btn { background: none; border: none; color: var(--blue-fg); cursor: pointer; font-size: 13px; text-decoration: underline; }
.sess-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }
.sess-tabs button { height: 30px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--text-2); font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit; }
.sess-tabs button.on { color: var(--on-btn-alt); border-color: var(--btn-alt); background: var(--btn-alt); }
.sess-list { display: flex; flex-direction: column; gap: 0; max-height: 240px; overflow-y: auto; }
.sess { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 10px 2px; }
.sess:first-child { border-top: 0; }
.sess-top { display: flex; align-items: center; gap: 8px; font-size: 14px; margin-bottom: 4px; }
.sess-top strong { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sess-ic { width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; flex-shrink: 0; background: var(--green-bg); color: var(--green); }
.sess-ic.warn { background: var(--amber-glow); color: var(--amber); }
.sess-ic svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.sess-act { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.mini { font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 8px; border: 1px solid var(--line-3); background: transparent; color: var(--text-2); cursor: pointer; text-decoration: none; font-family: inherit; }
.mini:hover { color: var(--text); background: var(--panel-2); }
.mini.warn { color: var(--amber); border-color: var(--amber); }
.sess-form { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
.sess-ft { font-size: 13px; font-weight: 700; color: var(--text); }
.sess-form input,
.sess-form select { height: 36px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--text); padding: 0 10px; font-size: 14px; font-family: inherit; }
.sess-form input:focus,
.sess-form select:focus { outline: none; border-color: var(--accent); }
.sess-hint { margin: 0; font-size: 13px; color: var(--text-2); }
.sess-err { color: var(--red); font-size: 13px; }
</style>