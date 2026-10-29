<template>
  <div class="app" :data-theme="theme">
    <!-- Topbar: merek, (kontrol peta di tengah, dari MapView), tema, notifikasi, operator -->
    <header class="topbar floating" role="banner">
      <div class="brand">
        <span class="brand-logo" aria-hidden="true">
          <img :src="logoSrc" alt="" />
        </span>
        <div class="brand-t"><strong>SiLacak</strong><span>Pemantauan pendakian</span></div>
      </div>
      <div class="top-right">
        <button class="tb-ic" type="button" @click="toggleTheme" title="Ganti tema terang/gelap" aria-label="Ganti tema terang atau gelap">
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          <svg v-else viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
          <svg class="tb-chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" /></svg>
        </button>
        <span class="tb-ic static" role="img" :aria-label="sosCount ? `${sosCount} alarm SOS aktif` : 'Tidak ada alarm SOS'" :title="sosCount ? `${sosCount} alarm SOS aktif` : 'Tidak ada alarm SOS'">
          <svg viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
          <i v-if="sosCount" class="tb-dot"></i>
        </span>
      </div>
    </header>

    <SosOverlay />
    <MapView :theme="theme" @toggle-theme="toggleTheme" />
    <BaseStatusBar />
    <WorkspacePanel />
    <MonitoringPanel />
    <!-- Setup lokasi / DEM / relay = pengaturan lanjutan (persiapan lokasi), tidak dibutuhkan operator harian -->
    <SetupPanel v-if="siteStore.showSetup && uiStore.advanced" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import WorkspacePanel from "./components/WorkspacePanel.vue";
import MapView from "./components/MapView.vue";
import MonitoringPanel from "./components/MonitoringPanel.vue";
import SosOverlay from "./components/SosOverlay.vue";
import SetupPanel from "./components/SetupPanel.vue";
import BaseStatusBar from "./components/BaseStatusBar.vue";
import { useBaseStore } from "./stores/base";
import { useUiStore } from "./stores/ui";
import { installAutoUnlock } from "./composables/useAlarmSound";
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

const logoSrc = computed(() =>
  `${import.meta.env.BASE_URL}${theme.value === "dark" ? "logo-dark.png" : "logo-light.png"}`
);

const hikerStore = useHikerStore();
const alertStore = useAlertStore();
// Titik merah lonceng = SOS saja (merah = SOS, disiplin warna). OFF_TRAIL (amber) tidak ikut dihitung di sini.
const sosCount = computed(() => alertStore.alerts.filter((a) => a.alert_type !== "OFF_TRAIL").length);
const siteStore = useSiteStore();
const sessionStore = useSessionStore();
const diagStore = useDiagnosticsStore();
const baseStore = useBaseStore();
const uiStore = useUiStore();
let diagTimer = null;
watch(() => hikerStore.selectedCode, (c) => diagStore.refresh(c));
onUnmounted(() => {
  clearInterval(diagTimer);
  baseStore.stop();
});

onMounted(() => {
  hikerStore.loadInitial();
  alertStore.loadInitial();
  siteStore.loadActive();
  sessionStore.loadActive();
  baseStore.start();
  installAutoUnlock();
  diagStore.refresh(hikerStore.selectedCode);
  diagTimer = setInterval(() => diagStore.refresh(hikerStore.selectedCode), 5000);
});

let lastSessionSync = 0;
useLiveStream((message) => {
  if (message.type === "position") {
    hikerStore.applyPositionUpdate(message.data);
    // Alat baru yang mulai mengirim data dibuatkan sesi OTOMATIS oleh database (tanpa event SSE).
    // Muat ulang daftar sesi sekali (maks. tiap 5 dtk) supaya banner "Belum check-in" langsung muncul tanpa refresh.
    if (!sessionStore.active.some((s) => s.hiker_code === message.data.hiker_code) && Date.now() - lastSessionSync > 5000) {
      lastSessionSync = Date.now();
      sessionStore.loadActive();
    }
  } else if (message.type === "alert") {
    alertStore.addAlert(message.data);
  } else if (message.type === "alert_resolved") {
    // Backend menyelesaikan alarm otomatis (mis. OFF_TRAIL saat pendaki kembali masuk perimeter).
    alertStore.resolveById(message.data.id);
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
/* Font: Inter (isi) + Plus Jakarta Sans (judul). Bila tidak ada internet, otomatis
   memakai font sistem (Segoe UI) sehingga tampilan tetap rapi. Untuk offline penuh,
   pasang paket @fontsource/inter dan @fontsource/plus-jakarta-sans lalu import di main.js. */
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap");

/* ══════════════════════════════════════
   PALET WARNA SiLacak (Forest + Warm Cream + Golden Orange)
   Satu-satunya sumber warna antarmuka. Komponen lain memakai variabel ini,
   jadi cukup diubah di sini.
   Makna warna semantik (lihat .kiro/steering/conventions.md, jangan dilanggar):
   --blue     = PENDAKI (marker). Biru, bukan hijau.
   --blue-fg  = biru terang untuk teks/ikon/garis di atas permukaan
   --green    = link kuat + base. Hijau sage.
   --amber    = link marginal + peringatan. Oranye sungguhan (BUKAN sama dengan --muted).
   --violet   = relay. Ungu (dipisah dari --accent trail supaya relay != trail).
   --accent   = trail / lokasi / tombol utama (Golden Orange).
   --muted    = menunggu data / placeholder (abu netral, bukan peringatan).
   --red      = SOS / bahaya nyata SAJA.
   --btn      = tombol aksi utama (Golden Orange). Mau ganti warna tombol? Ubah
                --btn, --btn-hover, --on-btn di bawah.
   --marker   = penanda pendaki normal (biru, mengikuti --blue)
══════════════════════════════════════ */
:root {
  /* DARK MODE */
  --bg: #101f19;          /* Deep Evergreen: latar utama */
  --panel: #172b22;       /* Forest Charcoal: sidebar / panel */
  --panel-2: #20382c;     /* Moss Slate: kartu / input */
  --panel-3: #172b22;     /* kotak dalam kartu */
  --line: #345141;        /* Muted Forest: border */
  --line-2: #345141;
  --line-3: #456654;
  --text: #f5f2e8;        /* Warm Ivory */
  --text-2: #b8c6b9;      /* Sage Gray */
  --muted: #a5ada5;       /* Stone Gray: menunggu / placeholder */
  --blue: #4d8fd6;        /* Sky Blue: PENDAKI (marker) */
  --blue-fg: #7fb0e6;     /* biru terang untuk teks/ikon di tema gelap */
  --blue-hover: #5f9fe0;  /* biru hover */
  --blue-glow: rgba(77, 143, 214, 0.16);
  --teal: #8cc9a0;
  --green: #8cc9a0;       /* hijau sage: link kuat + base */
  --green-bg: rgba(140, 201, 160, 0.16);
  --on-green: #101f19;    /* teks di atas isian hijau aman */
  --amber: #e0953a;       /* Orange: link marginal + peringatan (BEDA dari --muted) */
  --amber-glow: rgba(224, 149, 58, 0.16);
  --accent: #f5a623;      /* Golden Orange: lokasi / jalur / tombol (relay pindah ke --violet) */
  --accent-glow: rgba(245, 166, 35, 0.16);
  --violet: #9d84e0;      /* Violet: relay */
  --violet-glow: rgba(157, 132, 224, 0.18);
  --btn: #178650;         /* tombol utama: hijau tua */
  --btn-hover: #1d9a5e;
  --on-btn: #ffffff;      /* teks di atas tombol */
  --btn-glow: rgba(23, 134, 80, 0.35);   /* teks di atas tombol */
  --marker: #4d8fd6;      /* penanda pendaki normal (biru) */
  --on-marker: #fff;
  --red: #d95b49;         /* Terracotta Red: bahaya / SOS / putus */
  --red-bg: rgba(217, 91, 73, 0.13);
  --red-bg-2: rgba(217, 91, 73, 0.2);
  --red-line: rgba(217, 91, 73, 0.4);
  --red-pulse: rgba(217, 91, 73, 0.32);
  --radius: 14px;
  --rs: 12px;
  --lw: 340px;
  --rw: 380px;
  --gap: 12px;
  --edge: 12px;
  --top: 76px;
  --font: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-head: "Plus Jakarta Sans", "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
  --shadow-pop: 0 8px 24px rgba(0, 0, 0, 0.35);
  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.25);
}
[data-theme="light"] {
  /* LIGHT MODE */
  --bg: #f9f6eb;          /* Warm Cream: latar utama */
  --panel: #f9f6eb;       /* sidebar */
  --panel-2: #fffefa;     /* Pure Warm White: kartu / panel */
  --panel-3: #f9f6eb;     /* kotak dalam kartu */
  --line: #e4dfd2;        /* Soft Stone: border */
  --line-2: #e4dfd2;
  --line-3: #b8b19c;      /* border input (lebih gelap agar terlihat; kontras kasar) */
  --text: #18382b;        /* Deep Forest */
  --text-2: #4a5a4c;      /* Olive Gray gelap: label/hint (target >= 4.5:1, kasar) */
  --muted: #6e6a5c;       /* Stone gelap: teks menunggu/placeholder (kontras kasar) */
  --blue: #2f6fb0;        /* Sky Blue (gelap untuk krem): PENDAKI */
  --blue-fg: #2f6fb0;
  --blue-hover: #255c94;  /* biru hover */
  --blue-glow: rgba(47, 111, 176, 0.1);
  --teal: #3f7a57;
  --green: #3f7a57;       /* Sage Green (lebih gelap, kontras di krem): link kuat + base */
  --green-bg: rgba(63, 122, 87, 0.16);
  --on-green: #fffefa;
  --amber: #c07a1e;       /* Orange gelap: link marginal + peringatan */
  --amber-glow: rgba(192, 122, 30, 0.16);
  --accent: #e99a26;      /* Golden Orange: lokasi / jalur / tombol (relay pindah ke --violet) */
  --accent-glow: rgba(233, 154, 38, 0.16);
  --violet: #6f54c0;      /* Violet: relay */
  --violet-glow: rgba(111, 84, 192, 0.16);
  --btn: #0c6038;         /* tombol utama: hijau tua */
  --btn-hover: #094d2d;
  --on-btn: #f7f4d5;
  --btn-glow: rgba(12, 96, 56, 0.14);
  --marker: #2f6fb0;      /* penanda pendaki normal (biru) */
  --on-marker: #fffefa;
  --red: #c94f3d;         /* Terracotta Red: bahaya / SOS / putus */
  --red-bg: rgba(201, 79, 61, 0.11);
  --red-bg-2: rgba(201, 79, 61, 0.18);
  --red-line: rgba(201, 79, 61, 0.4);
  --red-pulse: rgba(201, 79, 61, 0.3);
  --shadow-pop: 0 8px 24px rgba(24, 56, 43, 0.18);
  --shadow-card: 0 1px 2px rgba(24, 56, 43, 0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font-family: var(--font); -webkit-font-smoothing: antialiased; }
/* PERBAIKAN LIGHT MODE: data-theme ada di .app, bukan di body. Tanpa baris color ini,
   semua teks tanpa warna eksplisit mewarisi putih dari body (tema gelap) dan tidak terbaca. */
.app { position: relative; width: 100vw; height: 100vh; overflow: hidden; color: var(--text); background: var(--bg); font-family: var(--font); }
.app input, .app select, .app textarea, .app button { font-family: inherit; }
.app input::placeholder { color: var(--muted); }
.app select option { background: var(--panel-2); color: var(--text); }

/* panel diciutkan -> lebar kolomnya mengecil sehingga peta (dan bilah yang menempel padanya) ikut melebar */
.app:has(.sidebar.left.collapsed) { --lw: 48px; }
.app:has(.sidebar.right.collapsed) { --rw: 48px; }

/* ── panel kartu membulat dengan jarak antar-panel (seperti dashboard referensi) ── */
.floating { position: absolute; z-index: 20; border: 1px solid var(--line); background: var(--panel); border-radius: var(--radius); }

/* ── sidebar kiri & kanan ── */
.sidebar { top: var(--top); bottom: var(--edge); display: flex; flex-direction: column; overflow: hidden; transition: width 0.15s ease; }
.sidebar.left { left: var(--edge); width: var(--lw); }
.sidebar.right { right: var(--edge); width: var(--rw); }
.sidebar.collapsed { width: 48px !important; height: 48px !important; top: var(--top); bottom: auto; border: 1px solid var(--line); border-radius: var(--rs); }
.sidebar.left.collapsed { left: var(--edge); }
.sidebar.right.collapsed { right: var(--edge); }
.sidebar.collapsed .ch { display: none !important; }

.sh { height: 58px; min-height: 58px; flex: 0 0 auto; display: flex; align-items: center; gap: 10px; padding: 0 14px; border-bottom: 1px solid var(--line); background: var(--panel); }
.sidebar.collapsed .sh { height: 100%; min-height: 100%; border: 0; padding: 0; justify-content: center; background: transparent; }
.tbtn { width: 34px; height: 34px; border-radius: 10px; border: 1px solid var(--line); background: transparent; color: var(--text-2); cursor: pointer; display: grid; place-items: center; flex-shrink: 0; }
.tbtn:hover { color: var(--text); background: var(--panel-2); }
.tbtn.on { color: var(--on-btn); background: var(--btn); border-color: var(--btn); }
.tbtn svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.slbl { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.slbl strong { font-family: var(--font-head); font-size: 17px; font-weight: 800; letter-spacing: -0.01em; color: var(--text); }
.slbl span { font-size: 13px; color: var(--text-2); font-weight: 500; }

.sb { min-height: 0; flex: 1; display: flex; flex-direction: column; gap: 0; padding: 0; overflow-y: auto; overflow-x: hidden; scrollbar-width: thin; scrollbar-color: var(--line-3) transparent; }

/* ── kartu ── */
/* seksi datar: tanpa kotak/bayangan, dipisah garis tipis */
.pnl { background: transparent; flex-shrink: 0; color: var(--text); }
.pnl + .pnl { border-top: 1px solid var(--line); }
.pnl-fill { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.ph { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 14px 16px 0; }
.ph .tl { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-width: 0; }
.ph .tl > svg.ic { width: 16px; height: 16px; flex-shrink: 0; fill: none; stroke: var(--blue-fg); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
/* judul kartu: lebih besar, tebal, font judul */
.ph .tl { font-family: var(--font-head); font-size: 15px; font-weight: 700; letter-spacing: -0.005em; color: var(--text); }
.ph .sv { flex-shrink: 0; font-size: 12px; color: var(--text-2); font-weight: 600; background: var(--panel-3); border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px; white-space: nowrap; }
.pb { padding: 12px 16px 16px; }

/* ── angka ringkasan ── */
.mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.mc { display: flex; align-items: center; gap: 10px; border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 10px 2px; min-width: 0; }
.mgrid .mc:nth-child(-n+2) { border-top: 0; }
.mc-ic { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; flex-shrink: 0; background: var(--blue-glow); color: var(--blue-fg); }
.mc-ic svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.mc-ic.sos { background: var(--red); color: #fff; font-size: 11px; font-weight: 800; letter-spacing: 0.02em; }
.mc-ic.ok { background: var(--green-bg); color: var(--green); }
.mc-t { min-width: 0; }
.mc strong { display: block; font-family: var(--font-head); font-size: 24px; font-weight: 800; line-height: 1.1; color: var(--text); }
.mc span.mc-l { display: block; margin-top: 2px; font-size: 12px; color: var(--text-2); font-weight: 600; }
.mc.alert strong { color: var(--red); }
.mc.good strong { color: var(--green); }

/* ── placeholder grafik ── */
.sgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.sc { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 8px 2px; }
.sc-h { display: flex; align-items: baseline; justify-content: space-between; gap: 4px; margin-bottom: 4px; }
.sc-h strong { font-size: 13px; font-weight: 700; color: var(--text-2); }
.sc-h span { font-size: 14px; font-weight: 700; }
.sc-w svg { width: 100%; height: 24px; display: block; }
.sc-w line { stroke: var(--line-3); stroke-width: 2; stroke-dasharray: 3 3; }
.ekg-c { border: 0; border-radius: 0; background: transparent; padding: 4px 0; }
.ekg-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
.ekg-h strong { font-size: 13px; font-weight: 700; color: var(--text-2); }
.ekg-h span { font-size: 14px; font-weight: 700; color: var(--text); }
.ekg-w { height: 56px; border-radius: 6px; border: 1px dashed var(--line-3); display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 13px; text-align: center; padding: 0 10px; }
.rf-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; margin-bottom: 10px; }
.rf-c { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 8px 2px; }
.rf-c strong { display: block; font-size: 13px; color: var(--text-2); margin-bottom: 3px; }
.rf-c span { display: block; font-size: 14px; font-weight: 700; line-height: 1.3; }
.lgnd { display: flex; gap: 8px 14px; flex-wrap: wrap; }
.lg { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-2); }
.lg.dim { opacity: 0.8; }
.sw.circle { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.sw.line { width: 14px; height: 4px; border-radius: 2px; display: inline-block; }

/* ── tab: yang aktif berwarna oranye penuh supaya jelas ── */
.tabs { display: grid; grid-template-columns: repeat(var(--tabs, 4), 1fr); gap: 6px; }
.tab { height: 38px; white-space: nowrap; padding: 0 4px; font-size: 13px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-3); color: var(--text-2); font-weight: 600; font-size: 14px; cursor: pointer; position: relative; font-family: inherit; }
.tab.active { color: var(--on-btn); background: var(--btn); border-color: var(--btn); }
.tab:hover:not(.active) { color: var(--text); background: var(--panel-3); }
.tab-badge { position: absolute; top: -7px; right: -4px; background: var(--red); color: #fff; font-size: 12px; font-weight: 700; border-radius: 999px; padding: 0 5px; line-height: 18px; min-width: 18px; }

/* ── kartu pendaki terpilih ── */
.selc { border: 0; border-radius: 0; background: transparent; padding: 0; min-height: 80px; color: var(--text); }
.selr { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 4px; }
.selr strong { font-size: 15px; font-weight: 700; }
.selb { font-size: 14px; color: var(--text-2); line-height: 1.7; }
.selb b { color: var(--text); font-weight: 600; margin-right: 3px; }
.selb .placeholder { color: var(--muted); }
.selb-row { display: flex; flex-wrap: wrap; gap: 0 12px; }
.selc-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.selc-id { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.selc-id strong { font-family: var(--font-head); font-size: 24px; font-weight: 800; color: var(--text); }
.selc-trail { font-size: 13px; color: var(--text-2); }
/* Badge status pendaki di kolom kiri (di bawah trail): satu baris yang bisa wrap, rapat,
   tidak menekan kolom kanan. Badge di sini dibuat lebih kecil dari .bdg umum supaya muat sebaris. */
.selc-badges { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; margin-top: 4px; }
.selc-badges .bdg { font-size: 12px; padding: 1px 8px; }
.selc-side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.selc-batt { display: flex; flex-direction: column; align-items: flex-end; margin-top: 3px; }
.selc-batt strong { font-family: var(--font-head); font-size: 26px; font-weight: 800; line-height: 1; color: var(--text); }
.selc-batt.hi strong { color: var(--green); }
.selc-batt.mid strong { color: var(--text); }
.selc-batt.lo strong { color: var(--red); }
.selc-batt span { font-size: 13px; color: var(--text-2); margin-top: 2px; }
.selc-seen { font-size: 13px; color: var(--text-2); margin-top: 4px; white-space: nowrap; }
.selc-grid { display: grid; gap: 0 16px; margin-top: 10px; }
.selc-grid.primary { grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr); }
.selc-grid.secondary { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.selc-cell { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 8px 2px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.selc-cell strong { font-size: 14px; font-weight: 700; line-height: 1.25; color: var(--text); white-space: normal; overflow-wrap: break-word; }
.selc-cell.sm strong { font-size: 13px; overflow-wrap: break-word; }
.selc-cell strong.placeholder { color: var(--muted); font-weight: 600; }
.selc-cell span { font-size: 13px; color: var(--text-2); }

/* ── daftar pendaki ── */
.hgrid { display: flex; flex-direction: column; gap: 0; }
.hcard { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 10px 8px; cursor: pointer; display: grid; grid-template-columns: auto 1fr auto auto; grid-template-areas: "num id bdg chev" ". gpx gpx gpx"; align-items: center; gap: 4px 10px; color: var(--text); }
.hcard:hover { background: var(--blue-glow); }
.hgrid .hcard:first-child { border-top: 0; }
.hcard.sel { background: var(--accent-glow); box-shadow: inset 3px 0 0 var(--accent); }
.hcard.sos { background: var(--red-bg); box-shadow: inset 3px 0 0 var(--red); }
.hcard.sel.sos { background: var(--red-bg-2); box-shadow: inset 3px 0 0 var(--red); }
.ht { display: contents; }
.hnum { grid-area: num; width: 26px; height: 26px; border-radius: 50%; background: var(--marker); color: var(--on-marker); font-size: 12px; font-weight: 700; display: grid; place-items: center; }
.hcard.sos .hnum { background: var(--red); color: #fff; }
.hid-wrap { grid-area: id; min-width: 0; display: flex; flex-direction: column; }
.hid { font-family: var(--font-head); font-size: 15px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
.ht .bdg { grid-area: bdg; }
.hchev { grid-area: chev; width: 14px; height: 14px; fill: none; stroke: var(--muted); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
.hcard > .gpx-btn { grid-area: gpx; justify-self: start; }
.hpos { font-size: 12px; color: var(--text-2); }

/* ── lencana status: hijau sage = aman, merah penuh = bahaya ── */
.bdg { font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 6px; border: 1px solid transparent; white-space: nowrap; }
.bdg.ok { background: var(--green); color: var(--on-green); border-color: var(--green); }
.bdg.bad { background: var(--red); color: #fff; border-color: var(--red); }
/* warn = PERINGATAN (perlu tindakan), oranye. BUKAN merah: merah = SOS saja. */
.bdg.warn { background: var(--amber); color: #fff; border-color: var(--amber); }
/* neutral = KETIDAKPASTIAN (mis. tanpa fix GPS), abu netral. Bukan bahaya, bukan peringatan. */
.bdg.neutral { background: transparent; color: var(--muted); border-color: var(--muted); }

/* ── daftar tautan / log / SOS ── */
.evl, .sosl, .lnkl { display: flex; flex-direction: column; gap: 0; }
.ev, .sosev, .lnk { border: 0; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 10px 4px; color: var(--text); }
.evl > .ev:first-child, .lnkl > .lnk:first-child, .sosl > .sosev:first-child { border-top: 0; }
.sosev { border-left: 3px solid var(--red); background: var(--red-bg); padding-left: 12px; }
.etit { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 15px; font-weight: 700; margin-bottom: 3px; color: var(--text); }
.emeta { font-size: 13px; color: var(--text-2); line-height: 1.6; }
.empty { border: 1px dashed var(--line-3); border-radius: 8px; min-height: 64px; display: flex; align-items: center; justify-content: center; color: var(--text-2); font-size: 14px; text-align: center; padding: 12px; line-height: 1.5; }
.ack-btn { background: var(--btn); color: var(--on-btn); border: none; border-radius: 8px; padding: 8px 14px; min-height: 40px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 8px; font-family: inherit; }
.ack-btn:hover:not(:disabled) { background: var(--btn-hover); }

/* ── topbar ── */
.topbar { top: var(--edge); left: var(--edge); right: var(--edge); height: 56px; z-index: 25; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 14px; }
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.brand-logo { width: 44px; height: 40px; display: grid; place-items: center; }
.brand-logo img { width: 100%; height: 100%; object-fit: contain; display: block; }
.brand-t { display: flex; flex-direction: column; line-height: 1.15; }
.brand-t strong { font-family: var(--font-head); font-size: 18px; font-weight: 800; color: var(--text); }
.brand-t span { font-size: 11.5px; color: var(--text-2); font-weight: 500; }
.top-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.tb-ic { position: relative; height: 36px; min-width: 36px; padding: 0 8px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel-2); color: var(--text-2); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
.tb-ic:hover { color: var(--text); background: var(--panel-3); }
.tb-ic.static { cursor: default; }
.tb-ic svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.tb-ic .tb-chev { width: 12px; height: 12px; }
.tb-dot { position: absolute; top: 6px; right: 7px; width: 8px; height: 8px; border-radius: 50%; background: var(--red); border: 1.5px solid var(--panel-2); }

/* ── kontrol peta: duduk di tengah topbar ── */
.map-ctl { top: calc(var(--edge) + 8px); left: 0; right: 0; margin: 0 auto; width: fit-content; max-width: calc(100vw - 2 * var(--edge) - 640px); z-index: 30; display: flex; align-items: center; justify-content: center; flex-wrap: nowrap; gap: 2px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px; padding: 2px; height: 40px; box-shadow: none; }
.mbtnn { min-width: 34px; height: 34px; border-radius: 8px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-family: inherit; white-space: nowrap; }
.mbtnn:hover:not(:disabled) { background: var(--panel-3); color: var(--text); }
.mbtnn svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.msep { width: 1px; height: 20px; background: var(--line); flex-shrink: 0; margin: 0 2px; }
.mbtnn.fit-btn { font-size: 13px; font-weight: 600; width: auto; padding: 0 12px; }
.mbtnn .seg { color: var(--muted); }
.mbtnn .seg.on { color: var(--text); font-weight: 700; }
.mbtnn .seg-sl { color: var(--line-3); }
/* Tombol toolbar peta = warna brand hijau (UI chrome), BUKAN --blue.
   --blue khusus penanda pendaki di peta (disiplin warna semantik). */
.app .map-ctl .mbtnn.pri { background: var(--green); color: var(--on-green); }
.app .map-ctl .mbtnn.pri:hover:not(:disabled) { background: var(--green); filter: brightness(1.08); color: var(--on-green); }
.app .map-ctl .mbtnn.on3d { background: var(--green); color: var(--on-green) !important; box-shadow: none; }
.app .map-ctl .mbtnn.on3d:hover:not(:disabled) { background: var(--green); filter: brightness(1.08); color: var(--on-green) !important; }

.conn-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--muted); margin-right: 6px; }
.conn-dot.live { background: var(--green); }

/* ── peta ── */
.maplibregl-map { background: transparent; font-family: var(--font); }
.maplibregl-ctrl-attrib { background: var(--panel) !important; color: var(--text-2) !important; font-size: 12px; }
.maplibregl-ctrl-attrib a { color: var(--text) !important; }
.sl-popup .maplibregl-popup-content { background: var(--panel-2); color: var(--text); border: 1px solid var(--line-3); font-family: var(--font); font-size: 14px; line-height: 1.55; box-shadow: none; padding: 10px 28px 10px 12px; border-radius: 8px; }
.sl-popup .maplibregl-popup-close-button { color: var(--text-2); font-size: 18px; }
.sl-popup.maplibregl-popup-anchor-bottom .maplibregl-popup-tip { border-top-color: var(--panel-2); }
.sl-popup.maplibregl-popup-anchor-top .maplibregl-popup-tip { border-bottom-color: var(--panel-2); }
.mk-anchor { width: 34px; height: 34px; }

/* penanda: pendaki = hijau, SOS = merah, base = hijau sage, relay = oranye */
.mk-site { min-width: 26px; height: 26px; padding: 0 5px; border-radius: 6px; display: grid; place-items: center; color: #fff; font-size: 13px; font-weight: 700; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.45); cursor: default; user-select: none; }
.mk-site.base { background: var(--green); color: var(--on-green); }
.mk-site.relay { background: var(--violet); color: #fff; }
.mk-site.relay.broken { opacity: 0.6; outline: 2px dashed var(--text); outline-offset: 2px; } /* bukan merah: merah = SOS */
.mk-site.drag { cursor: grab; box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.6); }
.mk-site.drag:active { cursor: grabbing; }
.mk-wrap { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.mk-h { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--marker); color: var(--on-marker); font-size: 12px; font-weight: 700; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.45); cursor: pointer; user-select: none; transition: width 0.15s ease, height 0.15s ease; }
.mk-h.sos { background: var(--red); color: #fff; }
.mk-h.selected { width: 32px; height: 32px; font-size: 13px; border-width: 3px; z-index: 10; }
/* cincin penanda pendaki terpilih: diam (tanpa animasi/glow) */
.mk-ring { position: absolute; width: 42px; height: 42px; border-radius: 50%; border: 2px solid var(--accent); pointer-events: none; }
.mk-ring.sos { border-color: var(--red); }

/* ── layar kecil: panel ditumpuk di bawah peta ── */
@media (max-width: 1100px) {
  html, body { overflow: auto; }
  .app { height: auto; min-height: 100vh; }
  #map { position: relative !important; min-height: 52vh; }
  .topbar { position: relative; top: auto; left: auto; right: auto; margin: 8px; }
  .sidebar { position: relative; left: auto !important; right: auto !important; top: auto; bottom: auto; width: auto !important; height: auto !important; margin: 8px; border: 1px solid var(--line); border-radius: var(--rs); }
  .sidebar.collapsed { width: auto !important; height: auto !important; }
  .map-ctl { top: 76px; max-width: 96vw; flex-wrap: wrap; height: auto; }
}

/* ── aksesibilitas ── */
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button:disabled { cursor: not-allowed; }
@media (pointer: coarse) {
  .tbtn { width: 42px; height: 42px; }
  .mbtnn { min-width: 44px; height: 44px; }
  .tab { height: 46px; }
  .mini, .lnk-btn { min-height: 38px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
@media (max-width: 600px) {
  .hgrid, .mgrid, .selc-grid.primary { grid-template-columns: 1fr; }
  .selc-grid.secondary { grid-template-columns: 1fr 1fr; }
}

/* ── penyesuaian warna & tipografi untuk komponen yang gayanya ada di file masing-masing ──
   (selektor sengaja lebih spesifik agar menang tanpa mengubah file komponen) */
.app .sess-warn .lnk-btn { color: var(--text); font-weight: 600; }
.app .sess-warn { color: var(--text); }
.app .sess strong { color: var(--text); font-size: 14px; }
.app .sess-form .sess-ft { font-family: var(--font-head); font-size: 15px; font-weight: 700; color: var(--text); }
.app .dp .dp-t { font-family: var(--font-head); font-size: 14px; font-weight: 700; color: var(--text); }
.app .setup .btn.active { background: var(--btn); border-color: var(--btn); color: var(--on-btn); }
.app .setup .stabs button.on { color: var(--text); }
.app .setup .nid { color: var(--text); }
.app .setup { border-top: 0; border-bottom: 0; border-right: 0; }
</style>