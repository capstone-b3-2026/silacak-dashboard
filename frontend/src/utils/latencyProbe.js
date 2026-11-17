// Pengukur latensi di sisi browser (fungsi murni, tanpa Vue/Pinia, diuji di Node).
//
// Satu paket posisi melewati: GPS pendaki -> radio -> base -> baca serial laptop -> masuk DB -> NOTIFY -> SSE -> browser -> layar.
// Payload SSE membawa: recorded_at (jam GPS), serial_read_at (laptop membaca baris serial), received_at (masuk DB).
// Browser mencatat: waktu SSE tiba (tSse) dan waktu layar selesai diperbarui (tRender).
//
// Batas yang harus dipahami:
// - Semua selisih selain gps_to_render memakai DUA jam yang sama-sama milik laptop (backend dan browser di mesin yang sama),
//   jadi sah tanpa sinkronisasi. gps_to_render memakai jam GPS pendaki dan HANYA bermakna bila jam laptop sinkron
//   (lihat clock_check di /diagnostics); karena itu hanya dihitung untuk paket berjam GPS.
// - "Tergambar" = Vue selesai memperbarui DOM + satu frame sudah dicat. Kanvas peta MapLibre bisa dicat satu frame lebih
//   lambat; selisihnya sekitar 16 ms pada layar 60 Hz. Ini perkiraan, bukan hasil pengukuran piksel.
// - Dashboard yang dibuka dari perangkat LAIN (bukan laptop base) mencampur dua jam berbeda: db_to_sse tidak valid.

export const PROBE_MAX = 300;

const ms = (v) => {
  if (v == null) return null;
  const t = typeof v === "number" ? v : Date.parse(v);
  return Number.isFinite(t) ? t : null;
};

// Satu sampel mentah dari payload SSE + dua waktu browser (epoch ms).
export function makeSample(data, tSse, tRender) {
  const d = data || {};
  return {
    hiker: d.hiker_code ?? null,
    recorded_ms: ms(d.recorded_at),
    serial_read_ms: ms(d.serial_read_at),
    received_ms: ms(d.received_at),
    time_from_gps: d.time_from_gps === true,
    sse_ms: tSse,
    render_ms: tRender,
  };
}

const diff = (a, b) => (a == null || b == null ? null : (a - b) / 1000);

// Tahap latensi (detik) untuk satu sampel; null bila datanya tidak ada.
export function stages(s) {
  return {
    serial_to_db_s: diff(s.received_ms, s.serial_read_ms),
    db_to_sse_s: diff(s.sse_ms, s.received_ms),
    sse_to_render_s: diff(s.render_ms, s.sse_ms),
    db_to_render_s: diff(s.render_ms, s.received_ms),
    gps_to_render_s: s.time_from_gps ? diff(s.render_ms, s.recorded_ms) : null,
  };
}

export function quantile(sorted, q) {
  if (!sorted.length) return null;
  const k = (sorted.length - 1) * q;
  const lo = Math.floor(k);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo);
}

const STAGE_KEYS = ["serial_to_db_s", "db_to_sse_s", "sse_to_render_s", "db_to_render_s", "gps_to_render_s"];

// Ringkasan per tahap: {n, min, p50, p95, max} dalam detik. Nilai negatif dipertahankan (itu sinyal jam tidak sinkron).
export function summarize(samples) {
  const out = {};
  for (const k of STAGE_KEYS) {
    const v = samples.map((s) => stages(s)[k]).filter((x) => x != null).sort((a, b) => a - b);
    out[k] = v.length ? { n: v.length, min: v[0], p50: quantile(v, 0.5), p95: quantile(v, 0.95), max: v[v.length - 1] } : null;
  }
  return out;
}

const iso = (t) => (t == null ? "" : new Date(t).toISOString());
const num = (x) => (x == null ? "" : x.toFixed(3));

// CSV untuk lampiran laporan (satu baris per paket).
export function toCsv(samples) {
  const head = ["hiker", "recorded_at", "serial_read_at", "received_at", "sse_at", "render_at", "time_from_gps", ...STAGE_KEYS];
  const rows = samples.map((s) => {
    const st = stages(s);
    return [s.hiker ?? "", iso(s.recorded_ms), iso(s.serial_read_ms), iso(s.received_ms), iso(s.sse_ms), iso(s.render_ms),
      s.time_from_gps ? 1 : 0, ...STAGE_KEYS.map((k) => num(st[k]))].join(",");
  });
  return [head.join(","), ...rows].join("\n");
}
