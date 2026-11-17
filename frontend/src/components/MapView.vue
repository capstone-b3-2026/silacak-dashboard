<template>
  <div id="map" ref="mapContainer"></div>

  <div class="map-ctl floating">
    <button class="mbtnn" @click="map?.zoomIn()" title="Perbesar peta" aria-label="Perbesar peta">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="11" y1="8" x2="11" y2="14" /><line x1="8" y1="11" x2="14" y2="11" /></svg>
    </button>
    <button class="mbtnn" @click="map?.zoomOut()" title="Perkecil peta" aria-label="Perkecil peta">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="8" y1="11" x2="14" y2="11" /></svg>
    </button>
    <div class="msep"></div>
    <button class="mbtnn fit-btn pri" @click="fitAll" title="Tampilkan semua pendaki di layar" aria-label="Tampilkan semua pendaki">Semua</button>
    <div class="msep"></div>
    <button
      class="mbtnn fit-btn" :aria-pressed="is3d" :disabled="!siteStore.ready" @click="toggle3d"
      :title="siteStore.ready ? 'Ganti tampilan 2D / 3D' : 'Upload DEM di Setup (Mode lanjutan) untuk mengaktifkan 3D'"
    >
      <span class="seg" :class="{ on: !is3d }">2D</span><span class="seg-sl">/</span><span class="seg" :class="{ on: is3d }">3D</span>
    </button>
    <button v-if="is3d" class="mbtnn fit-btn" @click="resetNorth" title="Balik menghadap utara">N</button>
    <button
      class="mbtnn fit-btn" :disabled="!topoReady" @click="toggleBasemap"
      :title="topoReady ? 'Ganti dasar peta: OSM (online) / Topo (offline, dari DEM)' : 'Peta topo offline belum ada — upload DEM di Setup'"
    ><span class="seg" :class="{ on: basemap !== 'topo' }">OSM</span><span class="seg-sl">/</span><span class="seg" :class="{ on: basemap === 'topo' }">TOPO</span></button>
    <div class="msep"></div>
    <button v-if="uiStore.advanced" class="mbtnn fit-btn" :class="{ on3d: siteStore.showSetup }" :aria-pressed="siteStore.showSetup" @click="siteStore.showSetup = !siteStore.showSetup" title="Pengaturan lanjutan: lokasi, DEM, relay &amp; perangkat"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>Setup</button>
    <button
      class="mbtnn fit-btn" :class="{ on3d: uiStore.advanced }" :aria-pressed="uiStore.advanced" @click="toggleMode"
      :title="uiStore.advanced ? 'Kembali ke tampilan harian (peta, pendaki, check-in, alarm)' : 'Buka pengaturan lanjutan: Setup lokasi, diagnostik link, data &amp; cadangan'"
    >{{ uiStore.advanced ? "Mode lanjutan" : "Mode harian" }}</button>
  </div>

  <!-- Legenda peta: dipindah dari panel kiri ke popover di pojok kiri-bawah peta supaya tidak
       memakan ruang panel. Isi = referensi arti warna penanda & garis (selalu penuh, tanpa dim). -->
  <div class="map-legend floating" ref="legendRef">
    <button
      class="mbtnn legend-btn" type="button" :aria-expanded="showLegend"
      aria-haspopup="dialog" @click="showLegend = !showLegend"
      title="Arti warna penanda &amp; garis di peta" aria-label="Legenda peta"
    >Legenda</button>
    <div v-if="showLegend" class="legend-pop" role="dialog" aria-label="Legenda peta">
      <div class="lgnd">
        <div class="lg"><span class="sw circle" style="background: var(--marker)"></span>Pendaki</div>
        <div class="lg"><span class="sw circle" style="background: var(--red)"></span>SOS</div>
        <div class="lg"><span class="sw circle" style="background: var(--violet)"></span>Relay</div>
        <div class="lg"><span class="sw circle" style="background: var(--green)"></span>Base</div>
        <div class="lg"><span class="sw line" style="background: var(--green)"></span>Link kuat</div>
        <div class="lg" title="Dua garis putus-putus kuning di kiri-kanan jalur. Lebarnya mengikuti pengaturan; di luar garis ini alarm 'di luar jalur' menyala."><span class="sw line" style="background: #e0b050; opacity: 0.8"></span>Koridor ±{{ Math.round(appConfigStore.perimeterM) }} m</div>
        <div class="lg" title="Garis oranye di peta: tautan relay dengan sinyal pas-pasan (fade margin tipis). Hijau = kuat."><span class="sw line" style="background: var(--amber)"></span>Link marginal</div>
      </div>
    </div>
  </div>

  <div v-if="is3d" class="map-hint floating">
    Geser kanan / Ctrl + geser = putar &amp; miringkan · dua jari di layar sentuh
  </div>

  <div v-if="notice" class="map-empty floating warn-toast">{{ notice }}</div>

  <div v-if="pendakiAktif === 0" class="map-empty floating">
    Belum ada data posisi masuk. Colok base ke laptop dan pastikan alat pendaki menyala, atau jalankan simulator.
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useHikerStore } from "../stores/hikers";
import { useAlertStore } from "../stores/alerts";
import { useSiteStore } from "../stores/site";
import { useDeviceStore } from "../stores/devices";
import { useSessionStore } from "../stores/sessions";
import { useUiStore } from "../stores/ui";
import { useAppConfigStore } from "../stores/appConfig";
import { buildRoute, routeFeatureCollection, trailCorridor, unresolvedMessage } from "../utils/routeGeo";

const props = defineProps({ theme: { type: String, default: "dark" } });
defineEmits(["toggle-theme"]);

const mapContainer = ref(null);
const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const siteStore = useSiteStore();
const uiStore = useUiStore();
const appConfigStore = useAppConfigStore(); // lebar koridor (stagnant_perimeter_m) dari pengaturan operator
const deviceStore = useDeviceStore(); // untuk memetakan ID relay di route_path ke posisinya
const sessionStore = useSessionStore(); // untuk menampilkan NAMA pendaki (bukan sekadar kode alat) di popup/tooltip
const is3d = ref(false);
const showLegend = ref(false); // popover legenda peta
const legendRef = ref(null); // wadah tombol+popover legenda (untuk deteksi klik di luar)
let map = null;
let mapReady = false;
let popup = null;
const markers = {}; // code -> { marker, el }
const basemap = ref(localStorage.getItem("silacak.basemap") || "topo"); // "osm" | "topo". Default topo (offline, dari DEM); kalau DEM belum ada, otomatis tampil OSM
const notice = ref("");
const topoReady = computed(() => !!siteStore.site?.dem_info?.topo && siteStore.site?.status === "ready");
let osmErrors = [];
let noticeTimer = null;
let siteMarkers = []; // marker base & relay
let demTopo = false; // apakah layer topo sudah terpasang untuk demId
let demId = null; // id site yang DEM-nya sedang terpasang di peta

// Pindah mode. Keluar dari mode lanjutan = tutup Setup & matikan mode klik-peta/geser relay,
// supaya peta tidak bisa terubah tanpa sengaja saat tampilan harian.
function toggleMode() {
  if (uiStore.advanced) {
    siteStore.showSetup = false;
    siteStore.editMode = null;
  }
  uiStore.toggleAdvanced();
}

const pendakiAktif = computed(() => Object.keys(hikerStore.hikers).length);

// Tutup popover legenda saat klik di luar wadahnya atau tekan Esc.
function onDocPointerDown(e) {
  if (showLegend.value && legendRef.value && !legendRef.value.contains(e.target)) showLegend.value = false;
}
function onDocKeydown(e) {
  if (e.key === "Escape") showLegend.value = false;
}

// Sebelum ada DEM aktif, peta mulai di sini. Begitu DEM siap, peta otomatis
// pindah & dikunci ke cakupan DEM-nya.
const START_CENTER = [110.453, -7.578];

// Palet jejak SENGAJA hanya warna dingin (toska/biru) yang belum punya arti lain di UI. Jangan tambahkan merah/merah muda
// (SOS), oranye/kuning (link marginal, jalur lokasi), hijau (link kuat, base), atau ungu (relay).
// 7 entri: H01, H02, H03, H11, H12 jatuh di indeks berbeda (tidak kembar).
const TRAIL_COLORS = ["#1f8a8a", "#6b4f9e", "#2a7ca3", "#8a6d3b", "#4f6d7a", "#a05a8c", "#5b8c5a"];
function colorFor(code) {
  let h = 0;
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) >>> 0;
  return TRAIL_COLORS[h % TRAIL_COLORS.length];
}

function isSos(code) {
  return alertStore.alerts.some((a) => a.hiker_code === code);
}

function markerHtml(code, sos, selected) {
  const label = String(code).replace(/\D/g, "") || code.slice(0, 2);
  const ring = selected ? `<span class="mk-ring${sos ? " sos" : ""}"></span>` : "";
  return `<div class="mk-wrap">${ring}<div class="mk-h${sos ? " sos" : ""}${selected ? " selected" : ""}">${label}</div></div>`;
}

// Pemetaan kode alat -> nama pendaki, pola sama seperti MonitoringPanel. Sesi yang dibuka otomatis
// (alat kirim data sebelum check-in) full_name-nya kosong -> jatuh ke kode.
const codeToName = computed(() => {
  const m = {};
  for (const s of sessionStore.active) {
    if (s.hiker_code && s.full_name) m[s.hiker_code] = s.full_name;
  }
  return m;
});
// Nama pendaki bila ada, selain itu null (pemanggil pakai kode alat sebagai judul cadangan).
function nameFor(code) {
  return (code && codeToName.value[code]) || null;
}

// Teks dari server (nama pendaki, kode) tidak boleh masuk innerHTML mentah. Popup MapLibre memakai
// setHTML, jadi escape dulu karakter yang bisa jadi tag/atribut sebelum disisipkan ke string HTML.
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function popupHtml(code, h, sos) {
  const alt = h.elevation != null ? `<br>${h.elevation} m` : "";
  const name = nameFor(code);
  // Judul = nama pendaki bila sudah check-in; kode alat jadi subjudul kecil. Tanpa nama: kode saja.
  const title = name ? `<b>${esc(name)}</b><br><span class="pp-code">${esc(code)}</span>` : `<b>${esc(code)}</b>`;
  return `${title}${sos ? " (SOS)" : ""}${alt}`;
}

function rasterPaint() {
  // Mode gelap: OSM asli terang, jadi diredupkan lewat paint raster
  // (MapLibre tidak pakai CSS filter tile kayak Leaflet).
  return props.theme === "dark"
    ? { "raster-brightness-max": 0.5, "raster-saturation": -0.35, "raster-contrast": 0.15 }
    : { "raster-brightness-max": 1, "raster-saturation": 0, "raster-contrast": 0 };
}

function buildStyle() {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    layers: [
      { id: "osm", type: "raster", source: "osm", paint: rasterPaint() },
    ],
  };
}

function applyRasterTheme() {
  if (!mapReady) return;
  const p = rasterPaint();
  for (const id of ["osm", "topo"])
    if (map.getLayer(id)) for (const k in p) map.setPaintProperty(id, k, p[k]);
}

function set3d(on) {
  if (on && !demId) return; // 3D butuh DEM
  is3d.value = on;
  if (!mapReady) return;
  if (on) {
    map.setTerrain({ source: "dem", exaggeration: 1.4 });
    map.easeTo({ pitch: 65, bearing: -20, duration: 900 });
  } else {
    map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    map.once("moveend", () => {
      if (!is3d.value) map.setTerrain(null);
    });
  }
}
function toggle3d() {
  set3d(!is3d.value);
}
function resetNorth() {
  map?.easeTo({ bearing: 0, duration: 600 });
}

function fitAll() {
  if (!map) return;
  const pts = Object.values(hikerStore.hikers).filter((h) => h.lat != null && h.lon != null);
  if (!pts.length) return;
  const b = new maplibregl.LngLatBounds();
  pts.forEach((h) => b.extend([h.lon, h.lat]));
  map.fitBounds(b, { padding: 90, maxZoom: 16, duration: 800 });
}

// ── marker ──────────────────────────────────────────────
function syncMarkers() {
  if (!mapReady) return;
  const seen = new Set();
  for (const code in hikerStore.hikers) {
    const h = hikerStore.hikers[code];
    if (h.lat == null || h.lon == null) continue;
    seen.add(code);
    const sos = isSos(code);
    const selected = hikerStore.selectedCode === code;
    let m = markers[code];
    if (!m) {
      const el = document.createElement("div");
      el.className = "mk-anchor";
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        hikerStore.selectHiker(code);
      });
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([h.lon, h.lat])
        .addTo(map);
      m = markers[code] = { marker, el };
    }
    m.marker.setLngLat([h.lon, h.lat]);
    m.el.innerHTML = markerHtml(code, sos, selected);
    // el.title = atribut DOM (teks murni, otomatis aman). Nama pendaki bila ada, lalu kode alat.
    const nm = nameFor(code);
    m.el.title = `${nm ? nm + " · " : ""}${code}${h.elevation != null ? ` · ${h.elevation} m` : ""}`;
  }
  for (const code in markers) {
    if (!seen.has(code)) {
      markers[code].marker.remove();
      delete markers[code];
    }
  }
  syncPopup();
}

function syncPopup() {
  const code = hikerStore.selectedCode;
  const h = code ? hikerStore.hikers[code] : null;
  if (!h || h.lat == null || h.lon == null) {
    popup?.remove();
    return;
  }
  popup.setLngLat([h.lon, h.lat]).setHTML(popupHtml(code, h, isSos(code)));
  if (!popup.isOpen()) popup.addTo(map);
}

// ── jejak (trek) ────────────────────────────────────────
function syncTrails() {
  if (!mapReady) return;
  const features = [];
  for (const code in hikerStore.tracks) {
    const pts = hikerStore.tracks[code];
    if (!pts || pts.length < 2) continue;
    features.push({
      type: "Feature",
      properties: { color: colorFor(code) },
      geometry: { type: "LineString", coordinates: pts.map(([lat, lon]) => [lon, lat]) },
    });
  }
  map.getSource("tracks")?.setData({ type: "FeatureCollection", features });
}

// ── rute paket NYATA: pendaki terpilih -> relay yang dilewati -> base ──
let routeNoticeKey = "";
function syncRoute() {
  if (!mapReady) return;
  const code = hikerStore.selectedCode;
  const h = code ? hikerStore.hikers[code] : null;
  const st = siteStore.site;
  const route = h
    ? buildRoute({ hiker: h, routePath: h.route_path, devices: deviceStore.devices, relays: st?.plan?.relays || [], base: st?.base || null })
    : { coords: [], hops: [], unresolved: [], direct: false, complete: false };
  map.getSource("route")?.setData(routeFeatureCollection(route));
  const msg = h ? unresolvedMessage(route) : "";
  const key = msg ? `${code}|${h.route_path}` : "";
  if (msg && key !== routeNoticeKey) showNotice(msg); // sekali per kombinasi pendaki+rute, bukan tiap paket
  routeNoticeKey = key;
}

// ── dasar peta: OSM (online) atau Topo (offline, dirender dari DEM) ──
function showNotice(msg, ms = 9000) {
  notice.value = msg;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (notice.value = ""), ms);
}
function applyBasemap() {
  if (!mapReady) return;
  const useTopo = basemap.value === "topo" && topoReady.value && !!map.getLayer("topo");
  const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  vis("osm", !useTopo);
  vis("topo", useTopo);
  vis("relief", !useTopo); // peta topo sudah punya bayangan sendiri, jangan ditumpuk dua kali
}
function setBasemap(v, { remember = true } = {}) {
  basemap.value = v;
  if (remember) localStorage.setItem("silacak.basemap", v);
  applyBasemap();
}
function toggleBasemap() {
  setBasemap(basemap.value === "topo" ? "osm" : "topo");
}
// OSM gagal dimuat beberapa kali berturut-turut = kemungkinan besar tidak ada internet.
function onMapError(e) {
  if (e?.sourceId !== "osm" || basemap.value !== "osm" || !topoReady.value) return;
  const now = Date.now();
  osmErrors = osmErrors.filter((t) => now - t < 15000).concat(now);
  if (osmErrors.length >= 4) {
    osmErrors = [];
    setBasemap("topo", { remember: false }); // otomatis: jangan ubah pilihan tersimpan
    showNotice("Tidak ada internet — beralih ke peta topo offline. Tekan TOPO/OSM untuk ganti.");
  }
}

// ── DEM aktif (dari upload di Setup) ────────────────────
// Tile elevasi disajikan backend di /api/v1/site-files/<id>/tiles. Ganti DEM =
// cukup upload lagi; sumber lama dilepas & yang baru dipasang otomatis.
let firstFit = true;
function syncDem() {
  if (!mapReady) return;
  const st = siteStore.site;
  const wantId = st?.status === "ready" ? st.id : null;
  const wantTopo = !!st?.dem_info?.topo;
  if (wantId === demId && wantTopo === demTopo) return;

  if (map.getTerrain()) map.setTerrain(null);
  if (map.getLayer("relief")) map.removeLayer("relief");
  if (map.getLayer("topo")) map.removeLayer("topo");
  if (map.getSource("topo")) map.removeSource("topo");
  if (map.getSource("dem")) map.removeSource("dem");
  if (map.getLayer("dem-bounds")) map.removeLayer("dem-bounds");
  if (map.getSource("dem-bounds")) map.removeSource("dem-bounds");
  demId = wantId;
  demTopo = wantTopo;

  if (!wantId) {
    map.setMaxBounds(null);
    map.setMinZoom(0);
    if (is3d.value) set3d(false);
    return;
  }
  const info = st.dem_info;
  map.addSource("dem", {
    type: "raster-dem",
    // worker MapLibre butuh URL absolut
    tiles: [`${window.location.origin}${st.tiles_url}`],
    tileSize: 256,
    minzoom: info.min_zoom,
    maxzoom: info.max_zoom,
    encoding: "terrarium",
    bounds: info.bounds,
    attribution: "Elevasi: DEM",
  });
  if (wantTopo) {
    map.addSource("topo", {
      type: "raster",
      tiles: [`${window.location.origin}${st.topo_url}`],
      tileSize: 256,
      minzoom: info.topo.min_zoom,
      maxzoom: info.topo.max_zoom, // satu level di atas DEM (lebih tajam saat di-zoom)
      bounds: info.bounds,
      attribution: "Topo: DEM",
    });
    map.addLayer({ id: "topo", type: "raster", source: "topo", paint: rasterPaint() }, map.getLayer("tracks") ? "tracks" : undefined);
  }
  map.addLayer(
    {
      id: "relief",
      type: "hillshade",
      source: "dem",
      paint: {
        "hillshade-exaggeration": 0.55,
        "hillshade-shadow-color": "#0a3a22",
        "hillshade-highlight-color": "#ffffff",
        "hillshade-accent-color": "#0c4a2c",
      },
    },
    map.getLayer("tracks") ? "tracks" : undefined
  );
  const [w, s, e, n] = info.bounds;
  // Tidak dikunci ke area DEM: bisa zoom out jauh sampai area DEM kelihatan kecil, dan batasnya digaris putus-putus.
  map.setMaxBounds(null);
  map.setMinZoom(0);
  map.addSource("dem-bounds", {
    type: "geojson",
    data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[w, s], [e, s], [e, n], [w, n], [w, s]] } },
  });
  map.addLayer({
    id: "dem-bounds", type: "line", source: "dem-bounds",
    // Batas DEM = kuning (konvensi warna; sama dengan trail putus-putus). MapLibre paint butuh hex literal.
    paint: { "line-color": "#e0b050", "line-width": 1.6, "line-dasharray": [3, 2] },
  });
  applyBasemap();
  map.fitBounds([[w, s], [e, n]], { padding: 40, duration: firstFit ? 0 : 800 });
  firstFit = false;
  if (is3d.value) map.setTerrain({ source: "dem", exaggeration: 1.4 });
}

// ── base, trail & relay hasil perencanaan ────────────────
function siteGeo() {
  const st = siteStore.site;
  const f = [];
  const trail = st?.trail || [];
  if (trail.length > 1)
    f.push({ type: "Feature", properties: { kind: "trail" }, geometry: { type: "LineString", coordinates: trail.map(([la, lo]) => [lo, la]) } });
  trail.forEach(([la, lo]) => f.push({ type: "Feature", properties: { kind: "pt" }, geometry: { type: "Point", coordinates: [lo, la] } }));
  const relays = st?.plan?.relays || [];
  if (st?.base && relays.length) {
    // titik[0] = base, titik[k] = relay ke-k; r.parent = node induk (0 = base). Rencana lama tanpa
    // `parent` = rantai berurutan.
    const nodes = [[st.base.lon, st.base.lat], ...relays.map((r) => [r.lon, r.lat])];
    relays.forEach((r, i) => {
      const loss = r.loss_db ?? (r.margin_m < 3 ? 6 : 0); // rencana lama hanya punya margin
      f.push({
        type: "Feature",
        // Warna link: tak-layak = merah literal #c94f3d (pengecualian terdokumentasi, bukan token SOS),
        // marginal = oranye #e8872f (~ --amber), kuat = hijau #3f8f5f. MapLibre paint butuh hex literal.
        properties: { kind: "link", color: r.link_ok === false ? "#c94f3d" : (r.fade_margin_db != null ? r.fade_margin_db < (st.params?.fade_margin_db ?? 10) : loss > 3) ? "#e8872f" : "#3f8f5f" },
        geometry: { type: "LineString", coordinates: [nodes[r.parent ?? i], nodes[i + 1]] },
      });
    });
  }
  return { type: "FeatureCollection", features: f };
}

function siteMarker(label, cls, lon, lat, title, { draggable = false, onDragEnd } = {}) {
  const el = document.createElement("div");
  el.className = `mk-site ${cls}${draggable ? " drag" : ""}`;
  el.textContent = label;
  el.title = title;
  el.addEventListener("click", (e) => e.stopPropagation());
  const m = new maplibregl.Marker({ element: el, anchor: "center", draggable }).setLngLat([lon, lat]).addTo(map);
  if (draggable) m.on("dragend", () => { const ll = m.getLngLat(); onDragEnd?.(ll.lat, ll.lng); });
  return m;
}

// Railing koridor: tampil saat trail punya >=2 titik. Lebarnya = stagnant_perimeter_m dari /app-config (nilai yang SAMA
// dipakai backend untuk alarm "di luar jalur" dan pemilihan jendela diam), jadi garis di peta ikut berubah begitu operator
// menyimpan ambang baru. trailCorridor aman untuk trail 0/1 titik (koridor kosong, tidak melempar).
function syncCorridor() {
  if (!mapReady) return;
  map.getSource("site-corridor")?.setData(trailCorridor(siteStore.site?.trail || [], appConfigStore.perimeterM));
}

function syncSite() {
  if (!mapReady) return;
  map.getSource("site")?.setData(siteGeo());
  syncCorridor();
  siteMarkers.forEach((m) => m.remove());
  siteMarkers = [];
  const st = siteStore.site;
  if (!st) return;
  if (st.base) siteMarkers.push(siteMarker("B", "base", st.base.lon, st.base.lat, `Base station${st.plan ? ` · ${st.plan.base_elev_m} m` : ""}`));
  const canDrag = siteStore.showSetup && siteStore.ready; // relay hanya bisa digeser saat panel Setup terbuka
  for (const r of st.plan?.relays || []) {
    const broken = r.link_ok === false;
    siteMarkers.push(siteMarker(
      `R${r.n}`, broken ? "relay broken" : "relay", r.lon, r.lat,
      `Relay ${r.n} · ${r.elev_m} m · hop ${r.hop_km} km · ${r.loss_db != null ? `redaman ${(r.loss_db + (r.veg_db ?? 0)).toFixed(1)} dB${r.fade_margin_db != null ? ` · margin ${r.fade_margin_db} dB` : ""}` : `margin ${r.margin_m} m`}${broken ? " · LINK PUTUS" : ""}${canDrag ? " · geser untuk memindah" : ""}`,
      { draggable: canDrag, onDragEnd: (lat, lon) => siteStore.moveRelay(r.n, lat, lon) },
    ));
  }
}

onMounted(() => {
  deviceStore.refresh(); // peta butuh pemetaan relay sejak awal (tanpa polling; polling hanya untuk panel Setup)
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: buildStyle(),
    center: START_CENTER,
    zoom: 14.5,
    maxZoom: 18,
    maxPitch: 82,
    attributionControl: { compact: true },
  });

  popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, offset: 18, className: "sl-popup" });
  popup.on("close", () => {
    // tombol X di popup = unselect, biar peta & panel kanan sepakat
    const code = hikerStore.selectedCode;
    if (code && hikerStore.hikers[code]) hikerStore.clearSelection();
  });

  map.on("error", onMapError);

  map.on("load", () => {
    map.addSource("tracks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "tracks",
      type: "line",
      source: "tracks",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": ["get", "color"], "line-width": 3.5, "line-opacity": 0.85 },
    });
    // "Railing" koridor perimeter (lebar dari pengaturan operator) di sekitar trail: dua garis putus-putus NON-merah (kuning pudar,
    // konsisten dengan trail #e0a800 / batas DEM #e0b050 — merah khusus SOS). Ditaruh sebelum site-trail
    // supaya z-order di bawah garis trail dan di bawah marker (marker = elemen DOM, selalu di atas).
    map.addSource("site-corridor", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "site-corridor", type: "line", source: "site-corridor", filter: ["==", ["get", "kind"], "corridor"],
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#e0b050", "line-width": 1.2, "line-opacity": 0.45, "line-dasharray": [1, 2] },
    });
    map.addSource("site", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "site-trail", type: "line", source: "site", filter: ["==", ["get", "kind"], "trail"],
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#e0a800", "line-width": 2.5, "line-dasharray": [2, 1.5] },
    });
    map.addLayer({
      id: "site-link", type: "line", source: "site", filter: ["==", ["get", "kind"], "link"],
      layout: { "line-cap": "round" },
      paint: { "line-color": ["get", "color"], "line-width": 3.5, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "site-pts", type: "circle", source: "site", filter: ["==", ["get", "kind"], "pt"],
      paint: { "circle-radius": 3.5, "circle-color": "#e0a800", "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
    });
    // rute paket: garis putus-putus terang berbingkai gelap (terbaca di tema gelap maupun terang) + cincin di relay yang dilewati
    map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "route-casing", type: "line", source: "route", filter: ["==", ["get", "kind"], "route"],
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#ffffff", "line-width": 6, "line-opacity": 0.7 },
    });
    map.addLayer({
      id: "route-line", type: "line", source: "route", filter: ["==", ["get", "kind"], "route"],
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#0c6038", "line-width": 2.5, "line-dasharray": [2, 1.5] },
    });
    map.addLayer({
      id: "route-hops", type: "circle", source: "route", filter: ["==", ["get", "kind"], "hop"],
      paint: { "circle-radius": 13, "circle-opacity": 0, "circle-stroke-color": "#0c6038", "circle-stroke-width": 2.5 },
    });
    mapReady = true;
    if (!navigator.onLine && basemap.value === "osm") basemap.value = "topo"; // browser sudah tahu sedang offline
    syncDem();
    syncSite();
    syncTrails();
    syncMarkers();
    syncRoute();
    if (is3d.value) set3d(true);
  });

  // mode edit (Setup): klik = taruh base / titik trail; selain itu klik kosong = unselect
  map.on("click", (e) => {
    if (siteStore.editMode) return siteStore.handleMapClick(e.lngLat.lat, e.lngLat.lng);
    hikerStore.clearSelection();
  });

  document.addEventListener("pointerdown", onDocPointerDown);
  document.addEventListener("keydown", onDocKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onDocKeydown);
  map?.remove();
  map = null;
  mapReady = false;
});

watch(() => hikerStore.hikers, () => { syncMarkers(); syncRoute(); }, { deep: true });
watch(() => deviceStore.devices, syncRoute, { deep: true });
watch(() => hikerStore.tracks, syncTrails, { deep: true });
watch(() => alertStore.alerts, syncMarkers, { deep: true });
watch(() => props.theme, applyRasterTheme);
watch(topoReady, applyBasemap);
watch(() => siteStore.site, () => { syncDem(); syncSite(); syncRoute(); }, { deep: true });
watch(() => siteStore.showSetup, syncSite);
watch(() => appConfigStore.perimeterM, syncCorridor);
watch(() => siteStore.editMode, (m) => { if (map) map.getCanvas().style.cursor = m ? "crosshair" : ""; });

watch(
  () => hikerStore.selectedCode,
  (code) => {
    syncMarkers();
    syncRoute();
    const h = code ? hikerStore.hikers[code] : null;
    if (h && h.lat != null && h.lon != null) map?.easeTo({ center: [h.lon, h.lat], duration: 600 });
  }
);
</script>

<style scoped>
/* peta = kartu membulat di antara dua panel, di bawah topbar */
#map {
  position: absolute; z-index: 0; background: var(--bg);
  top: var(--top); bottom: var(--edge);
  left: calc(var(--lw) + 2 * var(--edge)); right: calc(var(--rw) + 2 * var(--edge));
  border-radius: var(--radius); border: 1px solid var(--line); overflow: hidden;
}

.map-empty {
  position: absolute; top: calc(var(--top) + 12px); left: calc(var(--lw) + (100vw - var(--lw) - var(--rw)) / 2); transform: translateX(-50%);
  z-index: 20; color: var(--text-2); font-size: 14px; padding: 8px 14px;
  border-radius: 10px; max-width: min(60vw, 420px); text-align: center; background: var(--panel-2); border: 1px solid var(--line);
}
.map-hint {
  position: absolute; bottom: 84px; left: calc(var(--lw) + (100vw - var(--lw) - var(--rw)) / 2); transform: translateX(-50%);
  z-index: 20; color: var(--text-2); font-size: 13px; padding: 6px 12px;
  border-radius: 10px; white-space: nowrap; pointer-events: none; background: var(--panel-2); border: 1px solid var(--line);
}
.on3d { color: var(--blue-fg) !important; }
.warn-toast { color: var(--text); border-color: var(--accent); }
.mbtnn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Legenda peta: tombol di pojok kiri-bawah area peta (di dalam tepi kiri peta), popover buka ke atas.
   --lw = lebar sidebar kiri; peta mulai di calc(--lw + 2*--edge). z-index 30 = selevel .map-ctl. */
.map-legend { bottom: calc(var(--edge) + 44px); left: calc(var(--lw) + 2 * var(--edge) + 8px); z-index: 30; background: transparent; border: 0; }
.legend-btn { height: 34px; padding: 0 12px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; font-size: 13px; font-weight: 600; color: var(--text-2); }
.legend-btn:hover { color: var(--text); }
.legend-pop { position: absolute; bottom: calc(100% + 8px); left: 0; min-width: 160px; padding: 10px 12px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--rs); box-shadow: var(--shadow-pop); }

/* Subjudul kode alat di popup pendaki. Popup MapLibre di luar scope komponen -> :deep. */
:deep(.pp-code) { font-size: 12px; color: var(--muted); font-weight: 700; }

@media (max-width: 1100px) {
  #map { position: relative !important; inset: auto; margin: 8px; min-height: 52vh; }
  .map-empty, .map-hint { left: 50%; }
  .map-legend { left: 16px; }
}
</style>