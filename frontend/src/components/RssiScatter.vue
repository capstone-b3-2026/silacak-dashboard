<template>
  <div class="rs">
    <div class="rs-h">
      <strong>rssi vs jarak ke base</strong>
      <span>{{ pts.length }} titik · hanya paket langsung</span>
    </div>
    <div v-if="!pts.length" class="rs-empty">{{ baseSet ? "belum ada paket langsung dengan posisi" : "set base di Setup untuk menghitung jarak" }}</div>
    <svg v-else :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none">
      <g v-for="t in yTicks" :key="`y${t}`">
        <line :x1="L" :x2="W - R" :y1="sy(t)" :y2="sy(t)" class="grid" />
        <text :x="L - 4" :y="sy(t) + 3" text-anchor="end" class="tick">{{ t }}</text>
      </g>
      <g v-for="t in xTicks" :key="`x${t}`">
        <text :x="sx(t)" :y="H - 4" text-anchor="middle" class="tick">{{ t >= 1000 ? `${t / 1000} km` : `${t} m` }}</text>
      </g>
      <polyline v-if="fit" :points="fit.bandHi" class="band" />
      <polyline v-if="fit" :points="fit.bandLo" class="band" />
      <polyline v-if="fit" :points="fit.line" class="fit" />
      <circle v-for="(p, i) in pts" :key="i" :cx="sx(p.d)" :cy="sy(p.rssi)" r="2.6" class="dot" />
    </svg>
    <div v-if="fit" class="rs-fit">path loss exponent n ≈ <b>{{ fit.n.toFixed(2) }}</b> <span>(regresi log-distance, {{ fit.count }} titik · RSSI dBm)</span></div>
    <div v-if="fit" class="rs-fit">shadowing σ ≈ <b>{{ fit.sigma.toFixed(1) }} dB</b> <span>(simpangan baku residual; garis putus tipis = ±σ)</span></div>
    <div v-else-if="pts.length" class="rs-fit"><span>butuh ≥5 titik dengan rentang jarak cukup lebar untuk estimasi n</span></div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ packets: { type: Array, default: () => [] }, baseSet: Boolean });

const W = 300, H = 150, L = 30, R = 8, T = 8, B = 16;

// Hanya paket langsung (0 hop): untuk paket via relay, RSSI diukur di hop terakhir (relay → base),
// bukan di jarak pendaki → base, jadi memasukkannya akan merusak kalibrasi.
const pts = computed(() =>
  props.packets
    .filter((p) => p.rssi_dbm != null && p.dist_to_base_m != null && p.dist_to_base_m > 0 && !p.hop_count)
    .map((p) => ({ d: p.dist_to_base_m, rssi: p.rssi_dbm }))
);

const dMax = computed(() => Math.max(100, ...pts.value.map((p) => p.d)) * 1.05);
const rMin = computed(() => Math.floor((Math.min(...pts.value.map((p) => p.rssi)) - 5) / 10) * 10);
const rMax = computed(() => Math.ceil((Math.max(...pts.value.map((p) => p.rssi)) + 5) / 10) * 10);

const sx = (d) => L + (d / dMax.value) * (W - L - R);
const sy = (r) => T + ((rMax.value - r) / (rMax.value - rMin.value || 1)) * (H - T - B);

const yTicks = computed(() => {
  const out = [];
  for (let t = rMin.value; t <= rMax.value; t += 10) out.push(t);
  return out;
});
const xTicks = computed(() => {
  const step = dMax.value > 2000 ? 1000 : dMax.value > 600 ? 500 : dMax.value > 250 ? 200 : 100;
  const out = [];
  for (let t = step; t < dMax.value; t += step) out.push(t);
  return out;
});

// RSSI = a + b·log10(d)  →  n = −b/10  (kalau n ≈ 2 mendekati free space; hutan/medan biasanya 2.7–4)
// σ = simpangan baku residual regresi yang sama → estimasi variansi shadowing log-normal (plan 11.2).
const fit = computed(() => {
  const v = pts.value.filter((p) => p.d >= 10);
  if (v.length < 5) return null;
  const dmin = Math.min(...v.map((p) => p.d)), dmax = Math.max(...v.map((p) => p.d));
  if (dmax / dmin < 1.5) return null;
  const x = v.map((p) => Math.log10(p.d)), y = v.map((p) => p.rssi);
  const mx = x.reduce((a, b) => a + b, 0) / x.length, my = y.reduce((a, b) => a + b, 0) / y.length;
  const sxx = x.reduce((a, xi) => a + (xi - mx) ** 2, 0);
  if (!sxx) return null;
  const b = x.reduce((a, xi, i) => a + (xi - mx) * (y[i] - my), 0) / sxx;
  const a = my - b * mx;
  // Residual terhadap garis tren = deviasi shadowing (dB). Penyebut n−2 karena dua parameter (a, b) sudah diestimasi.
  const sse = x.reduce((acc, xi, i) => acc + (y[i] - (a + b * xi)) ** 2, 0);
  const sigma = Math.sqrt(sse / (v.length - 2));
  const yMin = T, yMax = H - B;
  const clampY = (py) => Math.min(Math.max(py, yMin), yMax);
  const trace = (off) => [0, 0.25, 0.5, 0.75, 1]
    .map((f) => { const d = dmin * (dmax / dmin) ** f; return `${sx(d).toFixed(1)},${clampY(sy(a + b * Math.log10(d) + off)).toFixed(1)}`; })
    .join(" ");
  return { n: -b / 10, sigma, count: v.length, line: trace(0), bandHi: trace(sigma), bandLo: trace(-sigma) };
});
</script>

<style scoped>
.rs { border: 0; border-bottom: 1px solid var(--line); border-radius: 0; background: transparent; padding: 0 0 12px; margin-bottom: 12px; }
.rs-h { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; margin-bottom: 6px; }
.rs-h strong { font-size: 11px; font-weight: 700; color: var(--text-2); letter-spacing: 0.06em; text-transform: uppercase; }
.rs-h span, .rs-fit span { font-size: 11px; color: var(--muted); }
.rs-empty { height: 56px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--muted); text-align: center; }
svg { width: 100%; height: 150px; display: block; }
.grid { stroke: var(--line); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 9px; }
.dot { fill: var(--accent); fill-opacity: 0.85; }
.fit { fill: none; stroke: var(--text-2); stroke-width: 1.5; stroke-dasharray: 4 3; }
.band { fill: none; stroke: var(--text-2); stroke-width: 1; stroke-opacity: 0.45; stroke-dasharray: 2 3; }
.rs-fit { font-size: 12px; color: var(--text-2); margin-top: 6px; }
.rs-fit b { color: var(--text); }
</style>