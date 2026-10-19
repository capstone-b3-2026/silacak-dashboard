// Tes logika rute (tanpa browser). Jalankan: node frontend/src/utils/routeGeo.test.mjs
import assert from "node:assert/strict";
import { buildRoute, parseRoute, routeFeatureCollection, unresolvedMessage } from "./routeGeo.js";

const base = { lat: -7.58, lon: 110.45 };
const relays = [
  { n: 1, lat: -7.581, lon: 110.451 },
  { n: 2, lat: -7.583, lon: 110.453 },
];
const devices = [
  { role: "relay", node_id: 5, plan_slot: 2 },
  { role: "relay", node_id: 6, plan_slot: 1 },
  { role: "relay", node_id: 7, plan_slot: null },
  { role: "tracker", node_id: 5, plan_slot: 1 }, // bukan relay: harus diabaikan
];
const hiker = { lat: -7.59, lon: 110.46 };

// parseRoute
assert.deepEqual(parseRoute("LANGSUNG"), []);
assert.deepEqual(parseRoute(""), []);
assert.deepEqual(parseRoute(null), []);
assert.deepEqual(parseRoute(undefined), []);
assert.deepEqual(parseRoute("R5"), [5]);
assert.deepEqual(parseRoute("R5>R6"), [5, 6]);
assert.deepEqual(parseRoute("R05>R006"), [5, 6]);
assert.deepEqual(parseRoute(" R5 > R6 "), [5, 6]);
assert.deepEqual(parseRoute("R5>X>R6"), [5, 6]); // token asing diabaikan
assert.deepEqual(parseRoute(42), []);

// rute 2 hop, urutan mengikuti route_path: pendaki -> R5(slot2) -> R6(slot1) -> base
let r = buildRoute({ hiker, routePath: "R5>R6", devices, relays, base });
assert.deepEqual(r.coords, [[110.46, -7.59], [110.453, -7.583], [110.451, -7.581], [110.45, -7.58]]);
assert.deepEqual(r.hops.map((h) => [h.nodeId, h.slot]), [[5, 2], [6, 1]]);
assert.equal(r.complete, true);
assert.equal(r.direct, false);
assert.equal(unresolvedMessage(r), "");

// langsung: garis lurus pendaki -> base
r = buildRoute({ hiker, routePath: "LANGSUNG", devices, relays, base });
assert.deepEqual(r.coords, [[110.46, -7.59], [110.45, -7.58]]);
assert.equal(r.direct, true);
assert.equal(r.complete, true);

// relay belum dipetakan (plan_slot null) / tidak terdaftar / slot tidak ada di rencana -> dilewati + dilaporkan
r = buildRoute({ hiker, routePath: "R7>R5>R99", devices, relays, base });
assert.deepEqual(r.unresolved, [7, 99]);
assert.deepEqual(r.hops.map((h) => h.nodeId), [5]);
assert.equal(r.complete, false);
assert.equal(unresolvedMessage(r), "Relay R7, R99 belum dipetakan ke posisi (tab Perangkat), jadi tidak digambar di rute.");
const stale = buildRoute({ hiker, routePath: "R5", devices: [{ role: "relay", node_id: 5, plan_slot: 9 }], relays, base });
assert.deepEqual(stale.unresolved, [5]); // rencana dihitung ulang -> slot 9 sudah tidak ada

// data kurang
assert.deepEqual(buildRoute({ hiker: null, routePath: "R5", devices, relays, base }).coords, []);
assert.deepEqual(buildRoute({ hiker: { lat: null, lon: null }, routePath: "R5", devices, relays, base }).coords, []);
r = buildRoute({ hiker, routePath: "R5", devices, relays, base: null }); // base belum diatur: tetap sampai relay terakhir
assert.equal(r.coords.length, 2);
assert.equal(r.complete, false);
r = buildRoute({ hiker, routePath: "LANGSUNG", devices, relays, base: null });
assert.deepEqual(r.coords, []); // tidak ada ujung lain -> tidak ada garis

// GeoJSON
const fc = routeFeatureCollection(buildRoute({ hiker, routePath: "R5>R6", devices, relays, base }));
assert.equal(fc.features.filter((f) => f.properties.kind === "route").length, 1);
assert.deepEqual(fc.features.filter((f) => f.properties.kind === "hop").map((f) => f.properties.slot), [2, 1]);
assert.deepEqual(routeFeatureCollection(buildRoute({ hiker: null, routePath: "R5", devices, relays, base })).features, []);

console.log("routeGeo: semua OK");
