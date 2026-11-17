// Logika murni untuk pengaturan operator (tanpa Vue/Pinia/fetch, jadi bisa diuji langsung di Node).

// Bawaan HANYA dipakai sebelum respons /app-config pertama tiba (atau bila gagal). Nilai sebenarnya selalu dari backend,
// supaya garis koridor di peta sama dengan yang dipakai alarm. 50 m = bawaan backend/app/core/config.py.
export const DEFAULT_PERIMETER_M = 50;

// Ambil lebar koridor yang valid dari respons /app-config; null bila tidak ada/tidak valid.
export function perimeterFromConfig(cfg) {
  const f = Array.isArray(cfg?.fields) ? cfg.fields.find((x) => x.key === "stagnant_perimeter_m") : null;
  const v = Number(f?.value);
  return Number.isFinite(v) && v > 0 ? v : null;
}
