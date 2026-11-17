// Tes perilaku wizard.html dengan DOM tiruan minimal (tanpa browser). Jalankan: node wizard_dom_test.js
// Yang diuji: alur tombol, isi payload PUT, tampilan error validasi, redirect, teks status base station.
// Yang TIDAK diuji: tampilan visual/CSS dan perilaku browser sungguhan.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const html = fs.readFileSync(path.join(__dirname, "..", "app", "static", "wizard.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.hidden = false;
    this.className = ""; this.textContent = ""; this.value = ""; this.type = ""; this.onclick = null;
    this._listeners = {};
    // style.setProperty dipakai wizard untuk mengisi progres slider; cukup no-op di DOM tiruan.
    this.style = { setProperty() {} }; }
  appendChild(c) { this.children.push(c); return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); return c; }
  // Wizard memakai addEventListener untuk slider/input/reset. Harness hanya perlu TIDAK melempar dan
  // menyimpan handler; tes memicu perilaku lewat .value + .onclick, bukan event sintetis.
  addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); }
  setAttribute(name, val) { if (name === "aria-label") this.ariaLabel = val; else this.dataset[name] = val; }
  get firstChild() { return this.children[0] || null; }
  all(tag) { return this.children.flatMap((c) => (c.tagName === tag ? [c] : []).concat(c.all(tag))); }
}

function makeEnv({ routes, path: pathname, search = "", win }) {
  const els = {};
  for (const m of html.matchAll(/\sid="([\w-]+)"/g)) els[m[1]] = new El("div");
  els["step-form"].hidden = true;
  els["base-pick"].hidden = true;
  const calls = [], timers = [];
  const loc = { pathname, href: "", search, origin: "http://127.0.0.1:8000" };
  const root = { _cls: [], _attrs: {}, classList: { add(c) { root._cls.push(c); } }, setAttribute(k, v) { root._attrs[k] = v; } };
  const doc = {
    documentElement: root,
    getElementById: (id) => { if (!els[id]) throw new Error("id tidak ada: " + id); return els[id]; },
    createElement: (t) => new El(t),
    querySelectorAll: (sel) => {
      // Dukung "#fields input" dan "#fields input[type=number]" (wizard memakai yang kedua di collectValues).
      assert.ok(sel === "#fields input" || sel === "#fields input[type=number]", "selector tak terduga: " + sel);
      const inputs = els["fields"].all("INPUT");
      return sel.includes("[type=number]") ? inputs.filter((i) => i.type === "number") : inputs;
    },
  };
  const fetch = async (url, opts = {}) => {
    const key = (opts.method || "GET") + " " + url;
    calls.push({ key, body: opts.body ? JSON.parse(opts.body) : null });
    const r = routes[key];
    if (!r) throw new Error("rute tak terduga: " + key);
    const [status, body] = typeof r === "function" ? r(opts) : r;
    return { ok: status < 400, status, text: async () => JSON.stringify(body) };
  };
  const ctx = vm.createContext({ document: doc, location: loc, window: win, fetch, console, JSON, Number,
    setTimeout: (f, ms) => { timers.push({ f, ms }); }, setInterval: () => 0 });
  vm.runInContext(script, ctx);
  return { els, calls, timers, loc, root };
}

const tick = () => new Promise((r) => setImmediate(r));
const FIELDS = [
  { key: "stagnant_radius_m", type: "float", min: 5, max: 500, step: 1, unit: "meter", label: "B", help: "h", default: 50, value: 50 },
  { key: "stagnant_perimeter_m", type: "float", min: 1, max: 500, step: 1, unit: "meter", label: "P", help: "h", default: 50, value: 50 },
  { key: "stagnant_window_inside_minutes", type: "int", min: 10, max: 1440, unit: "menit", label: "I", help: "h", default: 480, value: 480 },
  { key: "stagnant_window_outside_minutes", type: "int", min: 10, max: 1440, unit: "menit", label: "O", help: "h", default: 240, value: 240 },
  { key: "stagnant_check_interval_minutes", type: "int", min: 1, max: 60, unit: "menit", label: "C", help: "h", default: 2, value: 2 },
  { key: "data_retention_days", type: "int", min: 0, max: 3650, step: 1, unit: "hari", label: "R", help: "h", default: 0, value: 0 },
  { key: "offtrail_debounce_packets", type: "int", min: 1, max: 20, unit: "paket", label: "D", help: "h", default: 3, value: 3 },
];
const baseRoutes = (state, extra = {}) => Object.assign({
  "GET /api/v1/app-config": [200, { configured: false, fields: FIELDS }],
  "GET /api/v1/base/status": [200, Object.assign({ enabled: true, state: "searching", port: null, requested: "auto", last_error: null }, state)],
  "GET /api/v1/base/ports": [200, [{ device: "COM4", description: "USB-SERIAL CH340" }]],
}, extra);

(async () => {
  // 1) "Tidak tahu" -> PUT mode default -> redirect ke "/"
  let e = makeEnv({ routes: baseRoutes({}, { "PUT /api/v1/app-config": [200, { configured: true, fields: FIELDS }] }), path: "/awal" });
  await tick();
  // 7 isian angka (tiap field punya input number + slider range kembaran; hitung yang number saja)
  assert.strictEqual(e.els["fields"].all("INPUT").filter((i) => i.type === "number").length, 7, "7 isian harus dirender");
  assert.strictEqual(e.els["step-form"].hidden, true, "form tersembunyi dulu di /awal");
  e.els["btn-unsure"].onclick(); await tick();
  const put = e.calls.find((c) => c.key === "PUT /api/v1/app-config");
  assert.deepStrictEqual(put.body, { mode: "default", values: {} });
  e.timers.forEach((t) => t.f());
  assert.strictEqual(e.loc.href, "/");

  // 2) "Ya" -> form tampil -> ubah nilai -> PUT custom dengan ANGKA (bukan string)
  e = makeEnv({ routes: baseRoutes({}, { "PUT /api/v1/app-config": [200, { configured: true, fields: FIELDS }] }), path: "/awal" });
  await tick();
  e.els["btn-yes"].onclick();
  assert.strictEqual(e.els["step-form"].hidden, false);
  assert.strictEqual(e.els["step-ask"].hidden, true);
  const inputs = e.els["fields"].all("INPUT");
  inputs.find((i) => i.dataset.key === "stagnant_radius_m").value = "80";
  e.els["btn-save"].onclick(); await tick();
  const custom = e.calls.filter((c) => c.key === "PUT /api/v1/app-config").pop();
  assert.strictEqual(custom.body.mode, "custom");
  assert.deepStrictEqual(custom.body.values, {
    stagnant_radius_m: 80, stagnant_perimeter_m: 50, stagnant_window_inside_minutes: 480,
    stagnant_window_outside_minutes: 240, stagnant_check_interval_minutes: 2, data_retention_days: 0, offtrail_debounce_packets: 3,
  });

  // 3) isian kosong dikirim sebagai null (server yang menolak), pesan error server ditampilkan, TIDAK redirect
  e = makeEnv({ routes: baseRoutes({}, { "PUT /api/v1/app-config": [422, { detail: "'B' harus berupa angka antara 5 dan 500 (meter)." }] }), path: "/pengaturan" });
  await tick();
  assert.strictEqual(e.els["step-form"].hidden, false, "/pengaturan langsung ke form");
  e.els["fields"].all("INPUT").filter((i) => i.type === "number")[0].value = "";
  e.els["btn-save"].onclick(); await tick();
  assert.strictEqual(e.calls.filter((c) => c.key === "PUT /api/v1/app-config").pop().body.values.stagnant_radius_m, null);
  assert.ok(e.els["msg"].textContent.includes("harus berupa angka"));
  assert.strictEqual(e.els["msg"].className, "err");
  e.timers.forEach((t) => t.f());
  assert.strictEqual(e.loc.href, "", "tidak boleh pindah halaman saat error");

  // 4) teks status base station
  for (const [state, expected] of [
    [{ state: "connected", port: "COM4" }, "Terhubung ke COM4."],
    [{ state: "searching" }, "Belum ada base station terdeteksi"],
    [{ state: "ambiguous" }, "lebih dari satu perangkat"],
    [{ state: "reconnecting", last_error: "Port dipakai program lain" }, "Port dipakai program lain"],
  ]) {
    e = makeEnv({ routes: baseRoutes(state), path: "/pengaturan" });
    await tick(); await tick();
    assert.ok(e.els["base-text"].textContent.includes(expected), JSON.stringify(state) + " -> " + e.els["base-text"].textContent);
  }
  e = makeEnv({ routes: baseRoutes({ state: "connected", port: "COM4" }), path: "/pengaturan" });
  await tick(); await tick();
  assert.strictEqual(e.els["base-dot"].className, "dot ok");
  assert.strictEqual(e.els["base-pick"].hidden, false);
  assert.strictEqual(e.els["port-select"].children.length, 2, "Otomatis + 1 port");

  // 5) serial dimatikan -> pemilih port disembunyikan
  e = makeEnv({ routes: baseRoutes({ enabled: false, state: "off" }), path: "/pengaturan" });
  await tick(); await tick();
  assert.strictEqual(e.els["base-pick"].hidden, true);

  // 6) pilih port -> POST berisi nama port
  e = makeEnv({ routes: baseRoutes({ state: "ambiguous" }, { "POST /api/v1/base/port": [200, {}] }), path: "/pengaturan" });
  await tick(); await tick();
  e.els["port-select"].value = "COM4";
  e.els["btn-port"].onclick(); await tick();
  assert.deepStrictEqual(e.calls.find((c) => c.key === "POST /api/v1/base/port").body, { port: "COM4" });

  // 6b) slider/angka meter melangkah bulat (tanpa 10,504 dari step "any"); isian int tetap 1
  e = makeEnv({ routes: baseRoutes(), path: "/pengaturan" });
  await tick();
  const stepInputs = e.els["fields"].all("INPUT");
  assert.strictEqual(stepInputs.find((i) => i.dataset.key === "stagnant_perimeter_m").step, "1");
  assert.strictEqual(stepInputs.find((i) => i.dataset.key === "stagnant_radius_m").step, "1");
  assert.strictEqual(stepInputs.find((i) => i.dataset.key === "stagnant_perimeter_m").min, 1);

  // 7) mode tertanam (iframe di dashboard): simpan -> kabari induk lewat postMessage, TIDAK pindah halaman
  const sent = [];
  const win = { parent: { postMessage: (m, origin) => sent.push([m, origin]) } };
  e = makeEnv({ routes: baseRoutes({}, { "PUT /api/v1/app-config": [200, { configured: true, fields: FIELDS }] }), path: "/pengaturan", search: "?embed=1&theme=light", win });
  await tick();
  assert.ok(e.root._cls.includes("embed"), "kelas embed terpasang");
  assert.ok(e.els["actions"].children.includes(e.els["msg"]), "pesan harus ikut bar bawah (sticky) di mode tertanam");
  assert.strictEqual(e.root._attrs["data-theme"], "light");
  assert.strictEqual(e.els["btn-save"].textContent, "Simpan");
  e.els["fields"].all("INPUT").find((i) => i.dataset.key === "stagnant_perimeter_m").value = "120";
  e.els["btn-save"].onclick(); await tick();
  const emb = e.calls.filter((c) => c.key === "PUT /api/v1/app-config").pop();
  assert.strictEqual(emb.body.values.stagnant_perimeter_m, 120);
  assert.strictEqual(JSON.stringify(sent), JSON.stringify([[{ type: "silacak-settings-saved" }, "http://127.0.0.1:8000"]])); // objek dari konteks vm: bandingkan lewat JSON
  e.timers.forEach((t) => t.f());
  assert.strictEqual(e.loc.href, "", "mode tertanam tidak boleh redirect");
  // tanpa ?embed=1 perilaku lama tetap: redirect ke "/"
  e = makeEnv({ routes: baseRoutes({}, { "PUT /api/v1/app-config": [200, { configured: true, fields: FIELDS }] }), path: "/pengaturan", win });
  await tick(); e.els["btn-save"].onclick(); await tick(); e.timers.forEach((t) => t.f());
  assert.strictEqual(e.loc.href, "/");
  assert.strictEqual(sent.length, 1, "bukan embed -> tidak ada postMessage");

  console.log("wizard DOM: semua skenario OK");
})().catch((err) => { console.error(err); process.exit(1); });
