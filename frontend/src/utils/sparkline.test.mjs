// Tes logika crosshair sparkline (tanpa browser). Jalankan: node frontend/src/utils/sparkline.test.mjs
import assert from "node:assert/strict";
import { nearestIndexFromRatio } from "./sparkline.js";

// tepi: rasio 0 -> index 0; rasio 1 -> index n-1
assert.equal(nearestIndexFromRatio(0, 5), 0);
assert.equal(nearestIndexFromRatio(1, 5), 4);

// pembulatan ke terdekat (bukan floor): 0.5*4=2, 0.26*4=1.04, 0.24*4=0.96
assert.equal(nearestIndexFromRatio(0.5, 5), 2);
assert.equal(nearestIndexFromRatio(0.26, 5), 1);
assert.equal(nearestIndexFromRatio(0.24, 5), 1);
// 0.76*4=3.04 -> 3 (round). Dengan floor hasilnya juga 3, maka pakai kasus pemisah di bawah.
assert.equal(nearestIndexFromRatio(0.76, 5), 3);
// pembeda round vs floor: 0.7*4 = 2.8 -> round=3, floor=2
assert.equal(nearestIndexFromRatio(0.7, 5), 3);

// clamp di luar [0,1]
assert.equal(nearestIndexFromRatio(-0.5, 5), 0);
assert.equal(nearestIndexFromRatio(1.5, 5), 4);

// n === 1 -> selalu 0, rasio apa pun
assert.equal(nearestIndexFromRatio(0, 1), 0);
assert.equal(nearestIndexFromRatio(0.7, 1), 0);
assert.equal(nearestIndexFromRatio(5, 1), 0);

// n === 0 -> 0, aman (tidak melempar)
assert.equal(nearestIndexFromRatio(0.5, 0), 0);

// ratio non-angka (NaN) diperlakukan sebagai 0
assert.equal(nearestIndexFromRatio(NaN, 5), 0);

console.log("sparkline.test.mjs: semua assert lolos");
