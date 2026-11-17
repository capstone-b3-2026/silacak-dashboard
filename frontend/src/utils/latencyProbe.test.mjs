import assert from "node:assert/strict";
import { makeSample, quantile, stages, summarize, toCsv } from "./latencyProbe.js";

const T = Date.parse("2026-11-16T03:00:10.000Z");
const data = {
  hiker_code: "H01", time_from_gps: true,
  recorded_at: "2026-11-16T03:00:07.000Z",     // jam GPS
  serial_read_at: "2026-11-16T03:00:09.700Z",  // laptop membaca baris serial
  received_at: "2026-11-16T03:00:09.800Z",     // masuk DB
};
const s = makeSample(data, T, T + 120); // SSE tiba 200 ms setelah masuk DB, tergambar 120 ms kemudian
const st = stages(s);
assert.ok(Math.abs(st.serial_to_db_s - 0.1) < 1e-9);
assert.ok(Math.abs(st.db_to_sse_s - 0.2) < 1e-9);
assert.ok(Math.abs(st.sse_to_render_s - 0.12) < 1e-9);
assert.ok(Math.abs(st.db_to_render_s - 0.32) < 1e-9);
assert.ok(Math.abs(st.gps_to_render_s - 3.12) < 1e-9);

// paket tanpa jam GPS: latensi dari GPS TIDAK dihitung (jam laptop bukan jam GPS)
const noGps = stages(makeSample({ ...data, time_from_gps: false }, T, T + 10));
assert.equal(noGps.gps_to_render_s, null);
// data lama tanpa serial_read_at: tahap itu kosong, tahap lain tetap ada
const old = stages(makeSample({ ...data, serial_read_at: null }, T, T + 10));
assert.equal(old.serial_to_db_s, null);
assert.ok(old.db_to_sse_s > 0);
// payload kosong / waktu rusak tidak melempar
assert.doesNotThrow(() => stages(makeSample(null, 1, 2)));
assert.equal(stages(makeSample({ received_at: "bukan-tanggal" }, 1, 2)).db_to_sse_s, null);

// kuantil
const v = [1, 2, 3, 4, 100];
assert.equal(quantile(v, 0.5), 3);
assert.equal(quantile(v, 1), 100);
assert.equal(quantile([], 0.5), null);

// ringkasan: nilai negatif (jam tidak sinkron) dipertahankan, tidak dibuang
const many = [0.1, 0.2, 0.3, -2.0].map((d, i) => makeSample({ ...data, received_at: new Date(T - d * 1000).toISOString() }, T, T + 50 + i));
const sum = summarize(many);
assert.equal(sum.db_to_sse_s.n, 4);
assert.ok(Math.abs(sum.db_to_sse_s.min + 2.0) < 1e-9); // received_at 2 dtk di depan jam browser -> -2,0 dtk, TIDAK dibuang
assert.ok(Math.abs(sum.db_to_sse_s.max - 0.3) < 1e-9);
assert.equal(summarize([]).db_to_sse_s, null);

// CSV: header + satu baris per sampel, jumlah kolom konsisten
const csv = toCsv([s, s]).split("\n");
assert.equal(csv.length, 3);
assert.equal(csv[0].split(",").length, csv[1].split(",").length);
assert.ok(csv[1].startsWith("H01,2026-11-16T03:00:07.000Z"));
console.log("latencyProbe: semua OK");
