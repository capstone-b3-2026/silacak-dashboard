<template>
  <div class="app" :data-theme="theme">
    <SosOverlay />
    <MapView :theme="theme" @toggle-theme="toggleTheme" />
    <WorkspacePanel />
    <MonitoringPanel />
    <SetupPanel v-if="siteStore.showSetup" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import WorkspacePanel from "./components/WorkspacePanel.vue";
import MapView from "./components/MapView.vue";
import MonitoringPanel from "./components/MonitoringPanel.vue";
import SosOverlay from "./components/SosOverlay.vue";
import SetupPanel from "./components/SetupPanel.vue";
import { useSiteStore } from "./stores/site";
import { useHikerStore } from "./stores/hikers";
import { useAlertStore } from "./stores/alerts";
import { useSessionStore } from "./stores/sessions";
import { useDiagnosticsStore } from "./stores/diagnostics";
import { useLiveStream } from "./composables/useLiveStream";

const theme = ref("dark");
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
const siteStore = useSiteStore();
const sessionStore = useSessionStore();
const diagStore = useDiagnosticsStore();
let diagTimer = null;
watch(() => hikerStore.selectedCode, (c) => diagStore.refresh(c));
onUnmounted(() => clearInterval(diagTimer));

onMounted(() => {
  hikerStore.loadInitial();
  alertStore.loadInitial();
  siteStore.loadActive();
  sessionStore.loadActive();
  diagStore.refresh(hikerStore.selectedCode);
  diagTimer = setInterval(() => diagStore.refresh(hikerStore.selectedCode), 5000);
});

useLiveStream((message) => {
  if (message.type === "position") {
    hikerStore.applyPositionUpdate(message.data);
  } else if (message.type === "alert") {
    alertStore.addAlert(message.data);
  } else if (message.type === "session") {
    sessionStore.applyEvent(message.event, message.data);
    if (message.event === "closed") {
      hikerStore.removeHiker(message.data.hiker_code);
      alertStore.removeBySession(message.data.id);
    }
  }
});
</script>

<style>
/* ══════════════════════════════════════
   DESIGN TOKENS — sama persis kayak referensi (web_dashboard_node)
   biar dua-duanya konsisten kalau nanti dibandingin lagi.
══════════════════════════════════════ */
:root {
  --bg: #0d1117;
  --panel: #161b22;
  --panel-2: #1c2230;
  --panel-3: #20293a;
  --line: rgba(148, 168, 196, 0.09);
  --line-2: rgba(148, 168, 196, 0.16);
  --line-3: rgba(148, 168, 196, 0.26);
  --text: #dde5f0;
  --text-2: #a8b8cc;
  --muted: #6a7d93;
  --blue: #4d8fd6;
  --blue-glow: rgba(77, 143, 214, 0.18);
  --teal: #3dab7e;
  --green: #5aaa5a;
  --amber: #c8883a;
  --red: #c45050;
  --violet: #8068c8;
  --radius: 18px;
  --rs: 12px;
  --lw: 300px;
  --rw: 348px;
  --gap: 11px;
  --font: "Segoe UI", Inter, system-ui, -apple-system, sans-serif;
}
[data-theme="light"] {
  --bg: #eaeff6;
  --panel: rgba(255, 255, 255, 0.94);
  --panel-2: #ffffff;
  --panel-3: #f4f7fc;
  --line: rgba(50, 80, 120, 0.1);
  --line-2: rgba(50, 80, 120, 0.18);
  --line-3: rgba(50, 80, 120, 0.28);
  --text: #18273a;
  --text-2: #526070;
  --muted: #7a8fa8;
  --blue: #1c5fba;
  --blue-glow: rgba(28, 95, 186, 0.12);
  --teal: #0f7050;
  --green: #267026;
  --amber: #7a5010;
  --red: #922020;
  --violet: #4a339a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font-family: var(--font); -webkit-font-smoothing: antialiased; }
.app { position: relative; width: 100vw; height: 100vh; overflow: hidden; }

/* ── floating glass panels ── */
.floating { position: absolute; z-index: 20; border: 1px solid var(--line-2); background: var(--panel); }

/* ── sidebars ── */
.sidebar { top: var(--gap); bottom: var(--gap); border-radius: var(--radius); display: flex; flex-direction: column; overflow: hidden; transition: width 0.15s ease, height 0.15s ease; }
.sidebar.left { left: var(--gap); width: var(--lw); }
.sidebar.right { right: var(--gap); width: var(--rw); }
.sidebar.collapsed { width: 40px !important; height: 40px !important; top: var(--gap); bottom: auto; border-radius: 13px; }
.sidebar.collapsed .ch { display: none !important; }

.sh { height: 44px; min-height: 44px; flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 0 9px; border-bottom: 1px solid var(--line); }
.sidebar.collapsed .sh { height: 100%; min-height: 100%; border: 0; padding: 0; justify-content: center; }
.tbtn { width: 28px; height: 28px; border-radius: 9px; border: 1px solid var(--line-2); background: transparent; color: var(--muted); cursor: pointer; display: grid; place-items: center; flex-shrink: 0; transition: color 0.12s, background 0.12s; }
.tbtn:hover { color: var(--text); background: var(--panel-2); }
.tbtn svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.slbl { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
.slbl strong { font-size: 9px; letter-spacing: 0.13em; text-transform: uppercase; font-weight: 700; }
.slbl span { font-size: 8.5px; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600; }

.sb { min-height: 0; flex: 1; display: flex; flex-direction: column; gap: 7px; padding: 7px; overflow-y: auto; overflow-x: hidden; scrollbar-width: thin; scrollbar-color: var(--line-2) transparent; }

/* ── inner panels ── */
.pnl { border: 1px solid var(--line); border-radius: var(--rs); background: var(--panel-2); flex-shrink: 0; }
.pnl-fill { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.ph { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 10px 6px; border-bottom: 1px solid var(--line); }
.ph .tl { font-size: 8.5px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
.ph .sv { font-size: 9.5px; color: var(--text-2); font-weight: 600; }
.pb { padding: 7px 9px 9px; }

/* ── metrics ── */
.mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.mc { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 7px 9px; }
.mc strong { display: block; font-size: 16px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.05; }
.mc span { display: block; margin-top: 2px; font-size: 8px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.09em; font-weight: 700; }
.mc.alert strong { color: var(--red); }
.mc.good strong { color: var(--green); }

/* ── sparkline placeholders ── */
.sgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.sc { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 6px 7px 5px; }
.sc-h { display: flex; align-items: baseline; justify-content: space-between; gap: 4px; margin-bottom: 4px; }
.sc-h strong { font-size: 8px; font-weight: 700; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; }
.sc-h span { font-size: 10.5px; font-weight: 700; }
.sc-w svg { width: 100%; height: 24px; display: block; }
.sc-w line { stroke: var(--line-3); stroke-width: 2; stroke-dasharray: 3 3; }

/* ── EKG / timeline placeholder ── */
.ekg-c { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 7px 8px; }
.ekg-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 5px; }
.ekg-h strong { font-size: 8px; font-weight: 700; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; }
.ekg-h span { font-size: 10.5px; font-weight: 700; color: var(--text); }
.ekg-w { height: 56px; border-radius: 6px; background: rgba(0, 0, 0, 0.18); display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 9px; text-align: center; padding: 0 10px; }

/* ── rf params ── */
.rf-row { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 7px; }
.rf-c { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 6px 8px; }
.rf-c strong { display: block; font-size: 8px; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 3px; }
.rf-c span { display: block; font-size: 10.5px; font-weight: 700; line-height: 1.3; }
.lgnd { display: flex; gap: 8px; flex-wrap: wrap; }
.lg { display: flex; align-items: center; gap: 4px; font-size: 9px; color: var(--muted); }
.lg.dim { opacity: 0.5; }
.sw.circle { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.sw.line { width: 12px; height: 3px; border-radius: 1px; display: inline-block; }

/* ── tabs ── */
.tabs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.tab { height: 30px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--muted); font-weight: 700; font-size: 9px; cursor: pointer; letter-spacing: 0.05em; transition: all 0.12s; position: relative; }
.tab.active { color: var(--text); background: var(--panel-2); border-color: var(--line-2); }
.tab:hover:not(.active) { color: var(--text-2); }
.tab-badge { position: absolute; top: -5px; right: 3px; background: var(--red); color: #fff; font-size: 8px; font-weight: 700; border-radius: 999px; padding: 0 4px; line-height: 13px; min-width: 13px; }

/* ── selected card ── */
.selc { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 8px 10px; min-height: 80px; }
.selr { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 4px; }
.selr strong { font-size: 11.5px; font-weight: 700; letter-spacing: 0.05em; }
.selb { font-size: 9.5px; color: var(--text-2); line-height: 1.75; }
.selb b { color: var(--text); font-weight: 600; margin-right: 3px; }
.selb .placeholder { color: var(--muted); }
.selb-row { display: flex; flex-wrap: wrap; gap: 0 12px; }

/* ── selected-hiker: baterai & last-seen sebagai hero stat ── */
.selc-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 9px; }
.selc-id { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.selc-id strong { font-size: 15px; font-weight: 700; letter-spacing: 0.03em; }
.selc-trail { font-size: 8.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.selc-side { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex-shrink: 0; }
.selc-batt { display: flex; flex-direction: column; align-items: flex-end; margin-top: 3px; }
.selc-batt strong { font-size: 22px; font-weight: 800; line-height: 1; color: var(--text); }
.selc-batt.hi strong { color: var(--green); }
.selc-batt.mid strong { color: var(--amber); }
.selc-batt.lo strong { color: var(--red); }
.selc-batt span { font-size: 7.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 1px; }
.selc-seen { font-size: 8.5px; color: var(--muted); margin-top: 4px; white-space: nowrap; }

.selc-grid { display: grid; gap: 5px; margin-top: 7px; }
.selc-grid.primary { grid-template-columns: 1fr 1fr; }
.selc-grid.secondary { grid-template-columns: repeat(3, 1fr); }
.selc-cell { border: 1px solid var(--line); border-radius: 9px; background: var(--panel); padding: 6px 8px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.selc-cell strong { font-size: 12.5px; font-weight: 700; line-height: 1.25; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.selc-cell.sm strong { font-size: 10.5px; }
.selc-cell strong.placeholder { color: var(--muted); font-weight: 600; }
.selc-cell span { font-size: 7.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }

/* ── hiker grid ── */
.hgrid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 5px; }
.hcard { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 7px 8px; cursor: pointer; display: flex; flex-direction: column; gap: 4px; transition: border-color 0.12s, background 0.12s; }
.hcard:hover { border-color: var(--line-2); }
.hcard.sel { background: var(--blue-glow); border-color: rgba(77, 143, 214, 0.3); }
.hcard.sos { background: rgba(196, 80, 80, 0.1); border-color: rgba(196, 80, 80, 0.28); }
.hcard.sel.sos { background: rgba(196, 80, 80, 0.14); border-color: rgba(196, 80, 80, 0.35); }
.ht { display: flex; align-items: center; justify-content: space-between; gap: 5px; }
.hid { font-size: 10.5px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hpos { font-size: 8px; color: var(--muted); opacity: 0.8; }

/* ── badges ── */
.bdg { font-size: 7.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; padding: 2px 5px; border-radius: 999px; border: 1px solid transparent; white-space: nowrap; }
.bdg.ok { background: rgba(90, 170, 90, 0.12); color: var(--green); border-color: rgba(90, 170, 90, 0.18); }
.bdg.bad { background: rgba(196, 80, 80, 0.12); color: var(--red); border-color: rgba(196, 80, 80, 0.2); }

/* ── link/event/sos lists ── */
.evl, .sosl, .lnkl { display: flex; flex-direction: column; gap: 5px; }
.ev, .sosev, .lnk { border: 1px solid var(--line); border-radius: 9px; background: var(--panel-3); padding: 6px 8px; }
.sosev { border-left: 2px solid var(--red); background: rgba(196, 80, 80, 0.07); }
.etit { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 9.5px; font-weight: 700; margin-bottom: 2px; }
.emeta { font-size: 8.5px; color: var(--muted); line-height: 1.55; }
.empty { border: 1px dashed var(--line-2); border-radius: 9px; min-height: 56px; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 9px; text-align: center; padding: 10px; line-height: 1.5; }
.ack-btn { background: var(--red); color: #fff; border: none; border-radius: 6px; padding: 4px 10px; font-size: 10px; cursor: pointer; margin-top: 6px; }

/* ── map controls (top-center pill) ── */
.map-ctl { position: absolute; top: var(--gap); left: 50%; transform: translateX(-50%); z-index: 30; display: flex; align-items: center; gap: 1px; background: var(--panel); border: 1px solid var(--line-2); border-radius: 12px; padding: 3px; }
.mbtnn { width: 32px; height: 32px; border-radius: 9px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: grid; place-items: center; transition: background 0.12s, color 0.12s; }
.mbtnn:hover { background: var(--panel-2); color: var(--text); }
.mbtnn svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.msep { width: 1px; height: 20px; background: var(--line-2); flex-shrink: 0; margin: 0 1px; }
.mbtnn.fit-btn { font-size: 9px; font-weight: 700; letter-spacing: 0.06em; width: auto; padding: 0 8px; }

/* ── conn indicator ── */
.conn-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--muted); margin-right: 4px; transition: background 0.3s; }
.conn-dot.live { background: var(--green); }

/* ── maplibre overrides ── */
.maplibregl-map { background: transparent; font-family: var(--font); }
.maplibregl-ctrl-attrib { background: var(--panel) !important; color: var(--muted) !important; font-size: 9px; }
.maplibregl-ctrl-attrib a { color: var(--text-2) !important; }
.sl-popup .maplibregl-popup-content { background: var(--panel-2); color: var(--text); border: 1px solid var(--line-2); font-family: var(--font); font-size: 11px; line-height: 1.55; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3); padding: 10px 26px 10px 12px; border-radius: 10px; }
.sl-popup .maplibregl-popup-close-button { color: var(--text-2); font-size: 16px; }
.sl-popup.maplibregl-popup-anchor-bottom .maplibregl-popup-tip { border-top-color: var(--panel-2); }
.sl-popup.maplibregl-popup-anchor-top .maplibregl-popup-tip { border-bottom-color: var(--panel-2); }
.mk-anchor { width: 34px; height: 34px; }

.mk-site { min-width: 24px; height: 24px; padding: 0 4px; border-radius: 8px; display: grid; place-items: center; color: #fff; font-size: 9px; font-weight: 700; border: 2px solid rgba(255, 255, 255, 0.85); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35); cursor: default; user-select: none; }
.mk-site.base { background: var(--green); }
.mk-site.relay { background: var(--violet); }
.mk-site.relay.broken { opacity: 0.6; outline: 2px dashed var(--text); outline-offset: 2px; } /* bukan merah: merah = SOS */
.mk-site.drag { cursor: grab; box-shadow: 0 0 0 2px rgba(255,255,255,.55); }
.mk-site.drag:active { cursor: grabbing; }

/* ── markers ── */
.mk-wrap { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.mk-h { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: var(--blue); color: #fff; font-size: 8.5px; font-weight: 700; border: 2px solid rgba(255, 255, 255, 0.85); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3); cursor: pointer; user-select: none; transition: width 0.15s ease, height 0.15s ease, font-size 0.15s ease; }
.mk-h.sos { background: var(--red); border-color: rgba(255, 200, 200, 0.8); }
.mk-h.selected { width: 28px; height: 28px; font-size: 10px; border-width: 3px; z-index: 10; }

/* cincin "radar ping" buat marker yang lagi dipilih monitor - biar beda
   jelas dari marker lain, gak cuma gede dikit doang */
.mk-ring {
  position: absolute; width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid var(--blue); box-shadow: 0 0 10px 2px var(--blue-glow);
  animation: mk-pulse 1.5s ease-out infinite; pointer-events: none;
}
.mk-ring.sos { border-color: var(--red); box-shadow: 0 0 10px 2px rgba(196, 80, 80, 0.35); }
@keyframes mk-pulse {
  0% { transform: scale(0.9); opacity: 0.9; }
  70% { transform: scale(2.2); opacity: 0; }
  100% { opacity: 0; }
}

/* ── small screens: drop the floating overlay, stack everything ── */
@media (max-width: 900px) {
  html, body { overflow: auto; }
  .app { height: auto; min-height: 100vh; }
  #map { position: relative !important; min-height: 52vh; }
  .sidebar { position: relative; left: auto !important; right: auto !important; top: auto; bottom: auto; width: auto !important; height: auto !important; margin: 8px; border-radius: 16px; }
  .sidebar.collapsed { width: auto !important; height: auto !important; }
  .map-ctl { top: 56px; }
}
</style>