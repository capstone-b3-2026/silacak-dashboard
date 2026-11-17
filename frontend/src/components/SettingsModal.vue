<template>
  <transition name="set-fade">
    <div v-if="uiStore.showSettings" class="set-backdrop" @click.self="close">
      <div ref="card" class="set-card" role="dialog" aria-modal="true" aria-label="Pengaturan ambang deteksi" tabindex="-1">
        <button class="set-x" type="button" @click="close" title="Tutup (Esc)" aria-label="Tutup pengaturan">
          <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <iframe
          v-show="!failed" ref="frame" class="set-frame" :src="src" :style="{ colorScheme: theme === 'light' ? 'light' : 'dark' }" title="Pengaturan ambang deteksi"
          @load="onLoad"
        ></iframe>
        <p v-if="loading && !failed" class="set-note">Memuat pengaturan…</p>
        <p v-if="failed" class="set-note err">
          Halaman pengaturan tidak bisa dimuat di sini.
          <a href="/pengaturan" target="_blank" rel="noopener">Buka di jendela terpisah</a>
        </p>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useUiStore } from "../stores/ui";
import { useAppConfigStore } from "../stores/appConfig";

const props = defineProps({ theme: { type: String, default: "dark" } });
const uiStore = useUiStore();
const appConfig = useAppConfigStore();
const frame = ref(null);
const card = ref(null);
const loading = ref(true);
const failed = ref(false);
let closeTimer = null;

const src = computed(() => `/pengaturan?embed=1&theme=${props.theme === "light" ? "light" : "dark"}`);

function close() {
  clearTimeout(closeTimer);
  uiStore.closeSettings();
}

function onLoad() {
  loading.value = false;
  try {
    failed.value = !frame.value?.contentDocument?.getElementById("step-form");
  } catch (e) {
    failed.value = true;
  }
}

async function onMessage(e) {
  if (!uiStore.showSettings) return;
  if (e.origin !== window.location.origin || e.source !== frame.value?.contentWindow) return;
  if (e.data?.type !== "silacak-settings-saved") return;
  await appConfig.load(); 
  closeTimer = setTimeout(close, 700); 
}

function onKeydown(e) {
  if (e.key === "Escape" && uiStore.showSettings) close();
}

watch(
  () => uiStore.showSettings,
  async (open) => {
    if (!open) return;
    loading.value = true;
    failed.value = false;
    await nextTick();
    card.value?.focus();
  }
);
watch(src, () => {
  if (uiStore.showSettings) loading.value = true;
});

onMounted(() => {
  window.addEventListener("message", onMessage);
  document.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  clearTimeout(closeTimer);
  window.removeEventListener("message", onMessage);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<style scoped>
.set-backdrop { position: fixed; inset: 0; z-index: 3000; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; padding: 16px; }
.set-card { position: relative; width: min(700px, 100%); height: min(94vh, 980px); background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow-pop); overflow: hidden; outline: none; }
.set-frame { display: block; width: 100%; height: 100%; border: 0; background: transparent; }
.set-x { position: absolute; top: 12px; right: 22px; z-index: 3; width: 36px; height: 36px; border: 1px solid var(--line); border-radius: 50%; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--panel) 82%, transparent); color: var(--text-2); backdrop-filter: blur(4px); }
.set-x:hover { background: var(--panel-3); color: var(--text); }
.set-x:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.set-x svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.set-note { position: absolute; top: 70px; left: 24px; right: 24px; margin: 0; color: var(--text-2); font-size: 14px; }
.set-note.err { color: var(--text); }
.set-note a { color: var(--blue-fg); }
.set-fade-enter-active, .set-fade-leave-active { transition: opacity 0.15s ease; }
.set-fade-enter-from, .set-fade-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .set-fade-enter-active, .set-fade-leave-active { transition: none; } }
@media (max-width: 560px) { .set-backdrop { padding: 0; } .set-card { width: 100%; height: 100%; border-radius: 0; } }
</style>
