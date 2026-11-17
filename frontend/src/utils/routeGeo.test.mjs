// Tes logika rute (tanpa browser). Jalankan: node frontend/src/utils/routeGeo.test.mjs
import assert from "node:assert/strict";
import { buildRoute, haversineM, parseRoute, routeFeatureCollection, trailCorridor, trailSegments, unresolvedMessage } from "./routeGeo.js";

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

// ── haversineM (R = 6371008.8 m, konsisten dengan geo.py) ──
assert.equal(haversineM([-7.6, 110.4], [-7.6, 110.4]), 0); // titik sama -> 0
// 1 derajat lintang ~ 111195 m (R=6371008.8); toleransi 100 m
assert.ok(Math.abs(haversineM([0, 0], [1, 0]) - 111195) < 100);
// simetris
assert.ok(Math.abs(haversineM([-7.58, 110.45], [-7.59, 110.46]) - haversineM([-7.59, 110.46], [-7.58, 110.45])) < 1e-6);
// ~1 km di lintang -7.6 (bandingkan dengan tes geo.py Python): 0.009 derajat lintang ~ 1000 m
assert.ok(Math.abs(haversineM([-7.6, 110.4], [-7.591, 110.4]) - 1000) < 5);
// nilai sungguhan (number), bukan falsy kebetulan
assert.equal(typeof haversineM([-7.6, 110.4], [-7.6, 110.4]), "number");

// ── trailSegments ──
const tsBase = { lat: -7.58, lon: 110.45 };
// 0 titik -> total 0 & segments kosong
let ts = trailSegments(tsBase, []);
assert.equal(ts.totalM, 0);
assert.deepEqual(ts.segments, []);
// 1 titik tanpa base -> total 0, 0 segmen
ts = trailSegments(null, [[-7.581, 110.451]]);
assert.equal(ts.totalM, 0);
assert.equal(ts.segments.length, 0);
// base + 2 titik -> 2 segmen & total = jumlah m segmen
ts = trailSegments(tsBase, [[-7.581, 110.451], [-7.583, 110.453]]);
assert.equal(ts.segments.length, 2);
assert.ok(Math.abs(ts.totalM - (ts.segments[0].m + ts.segments[1].m)) < 1e-9);
assert.equal(ts.segments[0].fromLabel, "Base");
assert.equal(ts.segments[0].toLabel, "Titik 1");
assert.equal(ts.segments[1].toLabel, "Titik 2");
assert.ok(ts.totalM > 0);
// tanpa base + 2 titik -> 1 segmen
ts = trailSegments(null, [[-7.581, 110.451], [-7.583, 110.453]]);
assert.equal(ts.segments.length, 1);
assert.equal(ts.segments[0].fromLabel, "Titik 1");
assert.equal(ts.segments[0].toLabel, "Titik 2");
// titik duplikat -> segmen 0 m
ts = trailSegments(tsBase, [[-7.58, 110.45], [-7.58, 110.45]]);
assert.equal(ts.segments.length, 2);
assert.equal(ts.segments[1].m, 0); // titik1 == titik2
// base null diperlakukan konsisten (predikat baseOk boolean sungguhan)
assert.equal(trailSegments(undefined, []).totalM, 0);

// ── trailCorridor (railing di sekitar trail) ──
// INPUT [lat, lon]; OUTPUT koordinat [lon, lat]. 0/1 titik -> kosong, tidak melempar.
let cor = trailCorridor([], 50);
assert.deepEqual(cor.features, []); // trail kosong -> kosong
cor = trailCorridor([[-7.58, 110.45]], 50);
assert.deepEqual(cor.features, []); // 1 titik -> kosong, tanpa throw
cor = trailCorridor(undefined, 50);
assert.deepEqual(cor.features, []); // argumen tak valid -> kosong, tanpa throw

// 2 titik -> dua rel (kiri & kanan), masing-masing jumlah simpul = jumlah trail
const corTrail = [[-7.580, 110.450], [-7.583, 110.453]];
cor = trailCorridor(corTrail, 50);
assert.equal(cor.features.length, 2);
const leftF = cor.features.find((f) => f.properties.side === "left");
const rightF = cor.features.find((f) => f.properties.side === "right");
assert.ok(leftF && rightF);
assert.equal(leftF.properties.kind, "corridor");
assert.equal(leftF.geometry.coordinates.length, corTrail.length);
assert.equal(rightF.geometry.coordinates.length, corTrail.length);
// geseran tidak nol: rel menjauh dari titik trail aslinya (bandingkan simpul pertama)
const [laTrail0, loTrail0] = corTrail[0];
const [loL0, laL0] = leftF.geometry.coordinates[0];
const [loR0, laR0] = rightF.geometry.coordinates[0];
assert.ok(Math.abs(loL0 - loTrail0) > 1e-9 || Math.abs(laL0 - laTrail0) > 1e-9); // benar-benar digeser
// kiri & kanan kira-kira simetris terhadap garis trail (titik trail = tengah dua rel)
assert.ok(Math.abs((loL0 + loR0) / 2 - loTrail0) < 1e-9);
assert.ok(Math.abs((laL0 + laR0) / 2 - laTrail0) < 1e-9);
// output urutan [lon, lat]: lon ~110.45 (bukan -7.5), lat ~-7.58 -> pastikan tidak tertukar
assert.ok(loL0 > 100 && laL0 < 0);
// besar geseran kira-kira seukuran perimeter (50 m ~ 0.00045 derajat lintang), toleransi longgar
const offMagLat = Math.abs(laL0 - laTrail0);
assert.ok(offMagLat > 0 && offMagLat < 0.002);

// ── lebar koridor mengikuti argumen (dasar fitur "garis koridor ikut berubah saat ambang diatur") ──
{
  const trail = [[-7.600, 110.400], [-7.590, 110.400]]; // lurus ke utara: rel kiri/kanan = geser murni ke timur/barat
  const distOfRail = (m) => {
    const rail = trailCorridor(trail, m).features.find((f) => f.properties.side === "left").geometry.coordinates[0];
    return haversineM([trail[0][0], trail[0][1]], [rail[1], rail[0]]); // rail = [lon, lat] -> haversineM butuh [lat, lon]
  };
  for (const m of [10, 50, 120, 500]) assert.ok(Math.abs(distOfRail(m) - m) / m < 0.01, `rel pada ${m} m berjarak ${distOfRail(m)} m dari trail`);
  assert.ok(distOfRail(120) > distOfRail(50) * 2.3, "koridor 120 m harus lebih lebar dari 50 m");
  // nilai bawaan 50 m dipakai bila argumen tidak diberikan (perilaku lama tidak berubah)
  assert.deepEqual(trailCorridor(trail), trailCorridor(trail, 50));
}

console.log("routeGeo: semua OK");
