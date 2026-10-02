<template>
  <div id="map" ref="mapContainer"></div>

  <div class="map-ctl floating">
    <button class="mbtnn" @click="map?.zoomIn()" title="Zoom in">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="11" y1="8" x2="11" y2="14" /><line x1="8" y1="11" x2="14" y2="11" /></svg>
    </button>
    <button class="mbtnn" @click="map?.zoomOut()" title="Zoom out">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="8" y1="11" x2="14" y2="11" /></svg>
    </button>
    <div class="msep"></div>
    <button class="mbtnn fit-btn" @click="fitAll" title="Fit ke semua pendaki">FIT</button>
    <div class="msep"></div>
    <button
      class="mbtnn fit-btn" :class="{ on3d: is3d }" :disabled="!siteStore.ready" @click="toggle3d"
      :title="siteStore.ready ? 'Ganti tampilan 2D / 3D' : 'Upload DEM di Setup untuk mengaktifkan 3D'"
    >
      {{ is3d ? "3D" : "2D" }}
    </button>
    <button v-if="is3d" class="mbtnn fit-btn" @click="resetNorth" title="Balik menghadap utara">N</button>
    <button
      class="mbtnn fit-btn" :disabled="!topoReady" @click="toggleBasemap"
      :title="topoReady ? 'Ganti dasar peta: OSM (online) / Topo (offline, dari DEM)' : 'Peta topo offline belum ada — upload DEM di Setup'"
    >{{ basemap === "topo" ? "TOPO" : "OSM" }}</button>
    <div class="msep"></div>
    <button class="mbtnn fit-btn" :class="{ on3d: siteStore.showSetup }" @click="siteStore.showSetup = !siteStore.showSetup" title="Setup lokasi, DEM &amp; perangkat">SETUP</button>
    <button class="mbtnn" @click="$emit('toggle-theme')" title="Ganti tema terang/gelap">
      <svg v-if="theme === 'dark'" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      <svg v-else viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
    </button>
  </div>

  <div v-if="is3d" class="map-hint floating">
    Geser kanan / Ctrl + geser = putar &amp; miringkan · dua jari di layar sentuh
  </div>

  <div v-if="notice" class="map-empty floating warn-toast">{{ notice }}</div>

  <div v-if="pendakiAktif === 0" class="map-empty floating">
    Belum ada data posisi masuk — jalankan simulator atau tunggu data dari gateway.
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useHikerStore } from "../stores/hikers";
import { useAlertStore } from "../stores/alerts";
import { useSiteStore } from "../stores/site";

const props = defineProps({ theme: { type: String, default: "dark" } });
defineEmits(["toggle-theme"]);

const mapContainer = ref(null);
const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const siteStore = useSiteStore();
const is3d = ref(false);
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

const pendakiAktif = computed(() => Object.keys(hikerStore.hikers).length);

// Sebelum ada DEM aktif, peta mulai di sini. Begitu DEM siap, peta otomatis
// pindah & dikunci ke cakupan DEM-nya.
const START_CENTER = [110.453, -7.578];

const TRAIL_COLORS = ["#4d8fd6", "#c8883a", "#5aaa5a", "#8068c8", "#3dab7e", "#d6708a", "#c8b23a"];
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

function popupHtml(code, h, sos) {
  const bat = h.battery_pct != null ? `<br>bat ${h.battery_pct}%` : "";
  const alt = h.elevation != null ? `<br>${h.elevation} m` : "";
  return `<b>${code}</b>${sos ? " 🆘" : ""}${alt}${bat}`;
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
    m.el.title = `${code}${h.elevation != null ? ` · ${h.elevation} m` : ""}`;
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
        "hillshade-shadow-color": "#0b1410",
        "hillshade-highlight-color": "#ffffff",
        "hillshade-accent-color": "#1d2b22",
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
    let prev = [st.base.lon, st.base.lat];
    for (const r of relays) {
      const cur = [r.lon, r.lat];
      f.push({
        type: "Feature",
        properties: { kind: "link", color: r.link_ok === false ? "#d04a4a" : r.margin_m < 3 ? "#c8883a" : "#5aaa5a" },
        geometry: { type: "LineString", coordinates: [prev, cur] },
      });
      prev = cur;
    }
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

function syncSite() {
  if (!mapReady) return;
  map.getSource("site")?.setData(siteGeo());
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
      `Relay ${r.n} · ${r.elev_m} m · hop ${r.hop_km} km · margin ${r.margin_m} m${broken ? " · LINK PUTUS" : ""}${canDrag ? " · geser untuk memindah" : ""}`,
      { draggable: canDrag, onDragEnd: (lat, lon) => siteStore.moveRelay(r.n, lat, lon) },
    ));
  }
}

onMounted(() => {
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
    map.addSource("site", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "site-trail", type: "line", source: "site", filter: ["==", ["get", "kind"], "trail"],
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#e0b050", "line-width": 2.5, "line-dasharray": [2, 1.5] },
    });
    map.addLayer({
      id: "site-link", type: "line", source: "site", filter: ["==", ["get", "kind"], "link"],
      layout: { "line-cap": "round" },
      paint: { "line-color": ["get", "color"], "line-width": 3.5, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "site-pts", type: "circle", source: "site", filter: ["==", ["get", "kind"], "pt"],
      paint: { "circle-radius": 3.5, "circle-color": "#e0b050", "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
    });
    mapReady = true;
    if (!navigator.onLine && basemap.value === "osm") basemap.value = "topo"; // browser sudah tahu sedang offline
    syncDem();
    syncSite();
    syncTrails();
    syncMarkers();
    if (is3d.value) set3d(true);
  });

  // mode edit (Setup): klik = taruh base / titik trail; selain itu klik kosong = unselect
  map.on("click", (e) => {
    if (siteStore.editMode) return siteStore.handleMapClick(e.lngLat.lat, e.lngLat.lng);
    hikerStore.clearSelection();
  });
});

onBeforeUnmount(() => {
  map?.remove();
  map = null;
  mapReady = false;
});

watch(() => hikerStore.hikers, syncMarkers, { deep: true });
watch(() => hikerStore.tracks, syncTrails, { deep: true });
watch(() => alertStore.alerts, syncMarkers, { deep: true });
watch(() => props.theme, applyRasterTheme);
watch(topoReady, applyBasemap);
watch(() => siteStore.site, () => { syncDem(); syncSite(); }, { deep: true });
watch(() => siteStore.showSetup, syncSite);
watch(() => siteStore.editMode, (m) => { if (map) map.getCanvas().style.cursor = m ? "crosshair" : ""; });

watch(
  () => hikerStore.selectedCode,
  (code) => {
    syncMarkers();
    const h = code ? hikerStore.hikers[code] : null;
    if (h && h.lat != null && h.lon != null) map?.easeTo({ center: [h.lon, h.lat], duration: 600 });
  }
);
</script>

<style scoped>
#map { position: absolute; inset: 0; z-index: 0; background: var(--bg); }

.map-empty {
  position: absolute; top: 64px; left: 50%; transform: translateX(-50%);
  z-index: 20; color: var(--text-2); font-size: 12px; padding: 8px 14px;
  border-radius: 10px; max-width: min(80vw, 420px); text-align: center;
}
.map-hint {
  position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
  z-index: 20; color: var(--text-2); font-size: 10.5px; padding: 6px 12px;
  border-radius: 10px; white-space: nowrap; pointer-events: none;
}
.on3d { color: var(--blue) !important; }
.warn-toast { color: var(--amber); border-color: var(--amber); }
.mbtnn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>