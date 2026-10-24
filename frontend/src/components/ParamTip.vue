<!--
  Tooltip parameter ringan, zero-dependency. Dipakai di SetupPanel ("3 · Parameter relay"
  dan form tab Perangkat). Popup dirender via Teleport ke <body> + position:fixed supaya
  TIDAK terpotong oleh overflow panel Setup (.setup overflow:hidden) maupun sidebar (.sb).
  Posisi dihitung dari getBoundingClientRect tanda "?" saat hover/fokus, dijepit 8px dari
  tepi viewport, dan pindah ke bawah bila ruang di atas sempit. Muncul saat hover DAN fokus
  keyboard (aksesibel); Escape menutup. Terbaca di tema gelap & terang (pakai token).
-->
<template>
  <span
    ref="markRef"
    class="ptip-mark"
    tabindex="0"
    role="button"
    aria-label="Penjelasan parameter"
    @mouseenter="open"
    @mouseleave="close"
    @focus="open"
    @blur="close"
    @keydown.escape="close"
  >?</span>
  <Teleport to="body">
    <span v-if="shown" class="ptip-pop" :style="popStyle" role="tooltip">
      <slot />
    </span>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref } from "vue";

const markRef = ref(null);
const shown = ref(false);
const popStyle = ref({});

const POP_W = 260; // sinkron dengan max-width di CSS .ptip-pop
const MARGIN = 8; // jarak minimum dari tepi viewport

async function open() {
  shown.value = true;
  await nextTick();
  position();
}
function close() {
  shown.value = false;
}

function position() {
  const el = markRef.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Horizontal: pusatkan ke tanda, lalu jepit ke dalam viewport.
  let left = r.left + r.width / 2 - POP_W / 2;
  left = Math.max(MARGIN, Math.min(left, vw - POP_W - MARGIN));

  // Vertikal: default di atas tanda; kalau ruang atas sempit, taruh di bawah.
  const popup = document.querySelector(".ptip-pop");
  const h = popup ? popup.offsetHeight : 0;
  let top = r.top - h - 6;
  if (top < MARGIN) top = r.bottom + 6; // ruang atas tak cukup -> ke bawah
  top = Math.min(top, vh - h - MARGIN);

  popStyle.value = { left: `${left}px`, top: `${Math.max(MARGIN, top)}px`, width: `${POP_W}px` };
}

onBeforeUnmount(close);
</script>

<style scoped>
.ptip-mark {
  display: inline-grid; place-items: center; vertical-align: middle; margin-left: 4px;
  width: 15px; height: 15px; border-radius: 50%; border: 1px solid var(--line-3);
  color: var(--text-2); font-size: 10px; font-weight: 700; cursor: help; user-select: none;
}
.ptip-mark:hover, .ptip-mark:focus-visible { color: var(--text); border-color: var(--text-2); outline: none; }
</style>

<style>
/* Popup di-teleport ke <body>, jadi TIDAK scoped (tanpa data-attribute komponen). */
.ptip-pop {
  position: fixed; z-index: 1000; max-width: 260px; padding: 8px 10px; border-radius: 8px;
  background: var(--panel-2); color: var(--text); border: 1px solid var(--line-3);
  box-shadow: var(--shadow-pop); font: 500 12px/1.45 var(--font);
  text-transform: none; letter-spacing: 0; text-align: left; white-space: normal;
  pointer-events: none;
}
</style>
