// Tes logika murni pengaturan operator. Jalankan: node frontend/src/utils/appConfig.test.mjs
import assert from "node:assert/strict";
import { DEFAULT_PERIMETER_M, perimeterFromConfig } from "./appConfig.js";

const cfg = (v) => ({ fields: [{ key: "stagnant_radius_m", value: 50 }, { key: "stagnant_perimeter_m", value: v }] });
assert.equal(DEFAULT_PERIMETER_M, 50);
assert.equal(perimeterFromConfig(cfg(120)), 120);
assert.equal(perimeterFromConfig(cfg(37.5)), 37.5);
assert.equal(perimeterFromConfig(cfg("80")), 80); // string angka diterima
// tidak valid -> null (pemanggil mempertahankan nilai lama, bukan menggambar koridor lebar 0/NaN)
for (const bad of [0, -5, NaN, null, undefined, "abc"]) assert.equal(perimeterFromConfig(cfg(bad)), null, String(bad));
assert.equal(perimeterFromConfig({ fields: [] }), null);
assert.equal(perimeterFromConfig({}), null);
assert.equal(perimeterFromConfig(null), null);
console.log("appConfig: semua OK");
