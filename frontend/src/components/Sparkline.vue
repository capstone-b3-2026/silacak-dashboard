<template>
  <!-- wrapper relative supaya label nilai (overlay HTML) bisa absolute di atas grafik -->
  <div class="spark" ref="wrap">
    <svg
      ref="svg"
      :viewBox="`0 0 ${w} ${h}`"
      preserveAspectRatio="none"
      @mousemove="onMove"
      @mouseleave="onLeave"
    >
      <polyline v-if="points" :points="points" class="sp" :class="lineClass" />
      <line v-else x1="0" :y1="h / 2" :x2="w" :y2="h / 2" class="sp-base" />
      <template v-if="hover">
        <!-- garis vertikal (crosshair) + dot penanda di titik data terdekat -->
        <line class="sp-cross" :x1="hover.cx" y1="0" :x2="hover.cx" :y2="h" vector-effect="non-scaling-stroke" />
        <circle class="sp-dot" :class="lineClass" :cx="hover.cx" :cy="hover.cy" r="2.5" vector-effect="non-scaling-stroke" />
      </template>
    </svg>
    <!-- label nilai: overlay HTML (bukan <text> SVG karena preserveAspectRatio none bikin teks gepeng) -->
    <div v-if="hover" class="sp-val" :style="{ left: hover.leftPct + '%' }">{{ hover.text }}</div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { nearestIndexFromRatio } from "../utils/sparkline.js";

const props = defineProps({
  vals: { type: Array, default: () => [] }, // angka, terbaru di akhir
  w: { type: Number, default: 100 },
  h: { type: Number, default: 24 },
  pad: { type: Number, default: 2 }, // padding vertikal (sama seperti spark lama)
  lineClass: { type: String, default: "" }, // "rssi" / "lat" -> .sp.<lineClass>
  format: { type: Function, default: (v) => String(v) }, // nilai -> label
});

const svg = ref(null);
const hoverIndex = ref(null);

// Skala vertikal data: identik dengan spark() lama di WorkspacePanel (min..max, datar -> tengah).
const scale = computed(() => {
  const vals = props.vals;
  if (!vals.length) return null;
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  return { lo, hi };
});

// koordinat y titik ke-i dalam viewBox (rumus sama dengan spark())
function yAt(i) {
  const s = scale.value;
  const vals = props.vals;
  if (!s || vals.length <= 1) return props.h / 2;
  return props.h - props.pad - ((vals[i] - s.lo) / (s.hi - s.lo)) * (props.h - 2 * props.pad);
}

const points = computed(() => {
  const vals = props.vals;
  if (!vals.length) return "";
  if (vals.length === 1) return `0,${props.h / 2} ${props.w},${props.h / 2}`;
  const n = vals.length;
  return vals
    .map((v, i) => `${((i / (n - 1)) * props.w).toFixed(1)},${yAt(i).toFixed(1)}`)
    .join(" ");
});

// state crosshair saat hover: posisi viewBox (cx/cy), posisi overlay (leftPct), label nilai
const hover = computed(() => {
  const i = hoverIndex.value;
  const vals = props.vals;
  if (i == null || !vals.length) return null;
  const n = vals.length;
  const ratio = n <= 1 ? 0 : i / (n - 1);
  return {
    cx: ratio * props.w,
    cy: yAt(i),
    leftPct: ratio * 100,
    text: props.format(vals[i]),
  };
});

function onMove(e) {
  const el = svg.value;
  const vals = props.vals;
  if (!el || !vals.length) return;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0) return;
  const ratio = (e.clientX - rect.left) / rect.width;
  hoverIndex.value = nearestIndexFromRatio(ratio, vals.length);
}
function onLeave() {
  hoverIndex.value = null;
}
</script>

<style scoped>
.spark { position: relative; width: 100%; line-height: 0; }
/* tinggi svg: untuk kartu kecil diatur global .sc-w svg (24px), untuk grafik besar oleh .ekg-svg (56px);
   fallback mengikuti prop h via aspect-ratio tidak dipakai agar konsisten dengan tata letak lama */
.spark svg { width: 100%; height: 100%; display: block; }
/* garis grafik: salin dari WorkspacePanel karena .sp di sana scoped (tak mengalir ke child) */
.sp { fill: none; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.sp.rssi { stroke: var(--blue-fg); }
.sp.lat { stroke: var(--accent); }
.sp-base { stroke: var(--line-3); stroke-width: 2; stroke-dasharray: 3 3; }
/* crosshair & dot: warna netral, bukan merah (merah hanya SOS). Terbaca di tema gelap & terang. */
.sp-cross { stroke: var(--text-2); stroke-width: 1; stroke-dasharray: 2 2; }
.sp-dot { fill: var(--text-2); stroke: var(--panel-2); stroke-width: 1; }
.sp-dot.rssi { fill: var(--blue-fg); }
.sp-dot.lat { fill: var(--accent); }
/* label nilai di bawah crosshair; translateX(-50%) memusatkan, clamp tepi via max-width */
.sp-val {
  position: absolute;
  bottom: -4px;
  transform: translateX(-50%);
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--text-2);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.3;
  padding: 0 4px;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: none;
  max-width: 100%;
}
</style>
