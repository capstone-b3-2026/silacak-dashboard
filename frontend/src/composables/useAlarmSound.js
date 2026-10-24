import { reactive } from "vue";

// Bunyi alarm. Browser memblokir suara sampai ada interaksi pengguna: AudioContext yang dibuat tanpa klik
// berstatus "suspended" dan baru bunyi setelah resume() dipanggil dari klik/ketukan. Modul ini menyimpan
// satu AudioContext bersama + status "suara aktif / diblokir" untuk ditampilkan di UI.
export const sound = reactive({ enabled: false, blocked: false });

let ctx = null;

function getCtx() {
  const C = window.AudioContext || window.webkitAudioContext;
  if (!C) return null;
  if (!ctx) {
    ctx = new C();
    ctx.onstatechange = () => {
      sound.enabled = ctx.state === "running";
    };
  }
  return ctx;
}

function schedule(c, freq, type, gain, parts) {
  // parts: [[durasi, jeda sesudahnya], ...] dijadwalkan lewat currentTime supaya presisi
  let t = c.currentTime + 0.05;
  for (const [dur, gap] of parts) {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.value = gain;
    o.connect(g);
    g.connect(c.destination);
    o.start(t);
    o.stop(t + dur);
    t += dur + gap;
  }
}

const DOT = 0.13;
const DASH = DOT * 3;
const PATTERNS = {
  // Morse SOS (... --- ...): persis pola alarm SOS yang sebelumnya ada di SosOverlay
  sos: () => [900, "square", 0.18, [
    [DOT, DOT], [DOT, DOT], [DOT, DOT * 3],
    [DASH, DOT], [DASH, DOT], [DASH, DOT * 3],
    [DOT, DOT], [DOT, DOT], [DOT, 0],
  ]],
  // node tidak terdengar: dua nada sedang, beda dari SOS
  silent: () => [600, "triangle", 0.25, [[0.25, 0.15], [0.25, 0]]],
  // baterai rendah: satu nada panjang rendah
  battery: () => [450, "sine", 0.25, [[0.6, 0]]],
  // bunyi uji saat tombol "Aktifkan suara alarm" ditekan
  test: () => [880, "sine", 0.2, [[0.15, 0.08], [0.15, 0]]],
};

/** Dipanggil dari klik/ketukan pengguna. Mengembalikan true kalau suara benar-benar aktif. */
export async function enableSound() {
  const c = getCtx();
  if (!c) {
    sound.blocked = true;
    return false;
  }
  try {
    await c.resume();
  } catch (e) {
    /* dicek lewat state di bawah */
  }
  sound.enabled = c.state === "running";
  sound.blocked = !sound.enabled;
  if (sound.enabled) play("test");
  return sound.enabled;
}

export function play(kind) {
  try {
    const c = getCtx();
    if (!c) return;
    if (c.state !== "running") {
      c.resume?.().catch(() => {});
      if (c.state !== "running") {
        sound.enabled = false;
        sound.blocked = true; // UI menampilkan tombol "Aktifkan suara alarm"
        return;
      }
    }
    sound.enabled = true;
    sound.blocked = false;
    const [freq, type, gain, parts] = PATTERNS[kind]();
    schedule(c, freq, type, gain, parts);
  } catch (e) {
    /* alarm visual tetap tampil walau bunyi gagal */
  }
}

// Interaksi pertama di mana saja (klik / ketuk / tombol) otomatis membuka blokir suara,
// jadi operator tidak harus ingat menekan tombol kalau sudah pernah berinteraksi dengan halaman.
let unlockInstalled = false;
export function installAutoUnlock() {
  if (unlockInstalled || typeof document === "undefined") return;
  unlockInstalled = true;
  const unlock = async () => {
    const c = getCtx();
    if (!c) return;
    try {
      await c.resume();
    } catch (e) {
      /* abaikan */
    }
    sound.enabled = c.state === "running";
    if (sound.enabled) {
      sound.blocked = false;
      for (const ev of ["pointerdown", "keydown", "touchstart"]) document.removeEventListener(ev, unlock, true);
    }
  };
  for (const ev of ["pointerdown", "keydown", "touchstart"]) document.addEventListener(ev, unlock, true);
}
