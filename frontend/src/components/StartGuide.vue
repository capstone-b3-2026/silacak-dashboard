<template>
  <div v-if="open" class="guide-pop" role="dialog" aria-label="Langkah memulai">
    <div class="g-head">
      <div class="g-title">
        <strong>Langkah memulai</strong>
        <span>{{ doneCount }} dari 3 selesai</span>
      </div>
      <button class="g-close" type="button" aria-label="Tutup panduan" title="Tutup" @click="$emit('close')">
        <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
      </button>
    </div>
    <ol class="g-list">
      <li v-for="(s, i) in steps" :key="i" :class="{ done: s.done }">
        <span class="g-mark" aria-hidden="true">
          <svg v-if="s.done" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span class="g-body">
          <b>{{ s.title }}</b>
          <small>{{ s.done ? "Selesai" : s.hint }}</small>
        </span>
      </li>
    </ol>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useBaseStore } from "../stores/base";
import { useSessionStore } from "../stores/sessions";
import { useHikerStore } from "../stores/hikers";

defineProps({ open: { type: Boolean, default: false } });
defineEmits(["close"]);

const base = useBaseStore();
const sessions = useSessionStore();
const hikers = useHikerStore();

const hasHikerData = computed(() => Object.keys(hikers.hikers).length > 0);
const steps = computed(() => [
  {
    title: "Colok base ke laptop",
    hint: base.status?.state === "off" ? "Mode bridge luar: pastikan bridge berjalan." : "Tunggu status “Base terhubung” di bawah peta berwarna hijau.",
    done: base.status?.state === "connected" || (base.status?.state === "off" && hasHikerData.value),
  },
  {
    title: "Daftarkan pendaki",
    hint: "Isi form “Check-in pendaki” di panel Sesi pendakian.",
    done: sessions.active.some((s) => !s.auto_opened),
  },
  {
    title: "Pantau",
    hint: "Posisi pendaki muncul di peta begitu alatnya mengirim data.",
    done: hasHikerData.value,
  },
]);
const doneCount = computed(() => steps.value.filter((s) => s.done).length);
</script>

<style scoped>
.guide-pop {
  position: absolute; top: 68px; left: 12px; right: 12px; z-index: 6;
  background: var(--panel-2); color: var(--text); border: 1px solid var(--line-3);
  border-radius: var(--rs); box-shadow: var(--shadow-pop); padding: 14px;
}
.g-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
.g-title { display: flex; flex-direction: column; gap: 2px; }
.g-title strong { font-family: var(--font-head); font-size: 17px; font-weight: 700; color: var(--text); }
.g-title span { font-size: 13px; color: var(--text-2); }
.g-close { width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--line-3); background: transparent; color: var(--text-2); cursor: pointer; display: grid; place-items: center; flex-shrink: 0; }
.g-close:hover { background: var(--panel-3); color: var(--text); }
.g-close svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; }
.g-list { list-style: none; display: flex; flex-direction: column; gap: 14px; }
.g-list li { display: flex; gap: 12px; align-items: flex-start; font-size: 15px; line-height: 1.4; color: var(--text); }
.g-body b { font-weight: 700; color: var(--text); }
.g-list small { display: block; font-size: 13px; color: var(--text-2); margin-top: 2px; line-height: 1.5; }
.g-mark { flex: 0 0 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; font-size: 14px; font-weight: 700; border: 2px solid var(--line-3); color: var(--text-2); }
.g-mark svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.done .g-mark { background: var(--green); border-color: var(--green); color: var(--on-green); }
.done .g-body b { color: var(--text-2); font-weight: 600; }
</style>