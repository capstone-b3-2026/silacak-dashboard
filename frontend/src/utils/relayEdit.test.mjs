import assert from "node:assert/strict";
import { MAX_RELAYS, relayPoints, slotShiftAfterRemoval, withAdded, withMoved, withRemoved } from "./relayEdit.js";

const plan = { relays: [{ n: 1, lat: -7.6, lon: 110.4 }, { n: 2, lat: -7.59, lon: 110.41 }, { n: 3, lat: -7.58, lon: 110.42 }] };

assert.deepEqual(relayPoints(plan), [[-7.6, 110.4], [-7.59, 110.41], [-7.58, 110.42]]);
assert.deepEqual(relayPoints(null), []);
assert.deepEqual(relayPoints({}), []);

// tambah: dari NOL relay (belum ada plan sama sekali) sampai bertambah di ujung; koordinat dibulatkan 6 desimal
assert.deepEqual(withAdded(null, -7.1234567891, 110.9876543219), [[-7.123457, 110.987654]]);
assert.deepEqual(withAdded(plan, -7.5, 110.5).slice(-1), [[-7.5, 110.5]]);
assert.equal(withAdded(plan, -7.5, 110.5).length, 4);
const penuh = { relays: Array.from({ length: MAX_RELAYS }, (_, i) => ({ n: i + 1, lat: -7, lon: 110 })) };
assert.throws(() => withAdded(penuh, -7, 110), /Maksimal/);

// hapus: yang lain tetap berurutan; hapus semua -> daftar kosong (= "tanpa relay")
assert.deepEqual(withRemoved(plan, 2), [[-7.6, 110.4], [-7.58, 110.42]]);
assert.deepEqual(withRemoved(plan, 99), relayPoints(plan)); // nomor tak dikenal: tidak ada yang berubah
assert.deepEqual(withRemoved({ relays: [plan.relays[0]] }, 1), []);

// pindah: hanya relay n yang berubah
assert.deepEqual(withMoved(plan, 2, -7.55, 110.45), [[-7.6, 110.4], [-7.55, 110.45], [-7.58, 110.42]]);
assert.deepEqual(withMoved(null, 1, 0, 0), []);

// alat relay: hapus R2 -> alat di R2 dilepas, R3 -> R2, R4 -> R3 (urut naik, tanpa bentrok slot unik)
const devs = [{ id: 10, plan_slot: 4 }, { id: 11, plan_slot: 1 }, { id: 12, plan_slot: 2 }, { id: 13, plan_slot: 3 }, { id: 14, plan_slot: null }, { id: 15 }];
assert.deepEqual(slotShiftAfterRemoval(devs, 2), [[12, null], [13, 2], [10, 3]]);
assert.deepEqual(slotShiftAfterRemoval(devs, 4), [[10, null]]); // hapus yang terakhir: tidak ada yang digeser
assert.deepEqual(slotShiftAfterRemoval(devs, 9), []);
assert.deepEqual(slotShiftAfterRemoval(null, 1), []);

// tidak memutasi masukan
assert.equal(plan.relays.length, 3);
console.log("relayEdit: semua OK");
