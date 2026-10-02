<template>
  <div class="pnl">
    <div class="ph ph-toggle" @click="toggle" role="button" :aria-expanded="open" title="Buka/tutup panel sesi">
      <div class="tl">
        <svg class="chev" :class="{ open }" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" /></svg>
        sesi pendakian
        <span v-if="store.unregistered.length" class="bdg bad" style="margin-left: 6px">{{ store.unregistered.length }} belum check-in</span>
      </div>
      <div class="sv">{{ store.active.length }} aktif</div>
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
            <strong>{{ s.full_name || "Belum check-in" }}</strong>
            <span class="bdg" :class="s.auto_opened ? 'bad' : 'ok'">{{ s.hiker_code }}</span>
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
            <button v-if="s.status === 'active'" class="mini warn" @click="doCheckOut(s)">Check-out</button>
          </div>
        </div>
      </div>

      <!-- form check-in -->
      <form class="sess-form" @submit.prevent="submit">
        <div class="sess-ft">Check-in pendaki</div>
        <input v-model="form.hiker_code" list="alat-list" placeholder="Kode alat (mis. H01)" required maxlength="20" />
        <datalist id="alat-list"><option v-for="c in deviceCodes" :key="c" :value="c" /></datalist>
        <input v-model="form.full_name" placeholder="Nama pendaki" required />
        <input v-model="form.emergency_contact" placeholder="Kontak darurat (opsional)" />
        <input v-model="form.trail_name" placeholder="Jalur (opsional)" />
        <div v-if="error" class="sess-err">{{ error }}</div>
        <button class="ack-btn" style="background: var(--blue); width: 100%" :disabled="busy">{{ busy ? "..." : "Mulai sesi" }}</button>
      </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { fetchHikers, sessionGpxUrl } from "../services/api";
import { useSessionStore } from "../stores/sessions";

const store = useSessionStore();
const open = ref(localStorage.getItem("silacak.sessOpen") === "1"); // default terlipat
function toggle() {
  open.value = !open.value;
  localStorage.setItem("silacak.sessOpen", open.value ? "1" : "0");
}
const showHistory = ref(false);
const busy = ref(false);
const error = ref("");
const knownCodes = ref([]);
const form = reactive({ hiker_code: "", full_name: "", emergency_contact: "", trail_name: "" });

const list = computed(() => (showHistory.value ? store.history : store.active));
// saran kode alat: yang sudah dikenal sistem, kecuali yang sedang dipakai pendaki terdaftar
const deviceCodes = computed(() => {
  const busyCodes = new Set(store.active.filter((s) => !s.auto_opened).map((s) => s.hiker_code));
  return knownCodes.value.filter((c) => !busyCodes.has(c));
});

onMounted(async () => {
  try {
    knownCodes.value = (await fetchHikers()).map((h) => h.hiker_code);
  } catch (e) {
    /* saran kode alat saja yang hilang; form tetap bisa diketik manual */
  }
});

function fmt(iso) {
  return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function fillFor(code) {
  open.value = true;
  form.hiker_code = code;
  document.querySelector(".sess-form input:nth-of-type(2)")?.focus();
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
.chev { width: 10px; height: 10px; fill: none; stroke: currentColor; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; margin-right: 5px; transition: transform 0.15s; vertical-align: -1px; }
.chev.open { transform: rotate(90deg); }
.sess-warn { border: 1px solid rgba(196, 80, 80, 0.3); background: rgba(196, 80, 80, 0.08); border-radius: 9px; padding: 6px 8px; font-size: 9.5px; margin-bottom: 7px; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; }
.lnk-btn { background: none; border: none; color: var(--blue); cursor: pointer; font-size: 9.5px; text-decoration: underline; }
.sess-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 7px; }
.sess-tabs button { height: 26px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--muted); font-size: 9px; font-weight: 700; cursor: pointer; }
.sess-tabs button.on { color: var(--text); border-color: var(--line-2); background: var(--panel); }
.sess-list { display: flex; flex-direction: column; gap: 5px; max-height: 240px; overflow-y: auto; }
.sess { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 6px 8px; }
.sess-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; font-size: 10.5px; margin-bottom: 2px; }
.sess-act { display: flex; gap: 5px; margin-top: 5px; }
.mini { font-size: 9px; font-weight: 700; padding: 3px 8px; border-radius: 6px; border: 1px solid var(--line-2); background: transparent; color: var(--text-2); cursor: pointer; text-decoration: none; }
.mini:hover { color: var(--text); background: var(--panel-2); }
.mini.warn { color: var(--red); border-color: rgba(196, 80, 80, 0.35); }
.sess-form { display: flex; flex-direction: column; gap: 5px; margin-top: 9px; padding-top: 8px; border-top: 1px solid var(--line); }
.sess-ft { font-size: 8.5px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
.sess-form input { height: 28px; border-radius: 8px; border: 1px solid var(--line-2); background: var(--panel-3); color: var(--text); padding: 0 9px; font-size: 10.5px; font-family: inherit; }
.sess-form input:focus { outline: none; border-color: var(--blue); }
.sess-err { color: var(--red); font-size: 9.5px; }
</style>
