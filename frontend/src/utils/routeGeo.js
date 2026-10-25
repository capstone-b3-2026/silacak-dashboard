// Rute paket NYATA: pendaki -> relay-relay (urutan di route_path) -> base. Murni (tanpa Vue/MapLibre) supaya bisa diuji.
//
// route_path dari firmware berisi ID NODE relay mentah, mis. "R5>R6" (formatRoute di base_*.cpp), atau "LANGSUNG".
// Dashboard memetakan ID itu ke posisi lewat devices[].plan_slot ("relay ini dipasang di posisi R<n> pada rencana lokasi"),
// lalu mengambil koordinatnya dari rencana (plan.relays[].n/lat/lon).

/** "LANGSUNG" | "" | null -> []; "R5>R6" -> [5, 6]. Token yang tidak dikenali diabaikan. */
export function parseRoute(routePath) {
  if (!routePath || typeof routePath !== "string") return [];
  const ids = [];
  for (const tok of routePath.split(">")) {
    const m = /^\s*R(\d+)\s*$/i.exec(tok);
    if (m) ids.push(Number(m[1]));
  }
  return ids;
}

const hasPos = (p) => !!p && typeof p.lat === "number" && typeof p.lon === "number";

/**
 * @param hiker   {lat, lon} posisi terakhir pendaki (last known fix)
 * @param routePath string dari paket terakhir
 * @param devices daftar perangkat dari /devices (role, node_id, plan_slot)
 * @param relays  plan.relays dari lokasi aktif ([{n, lat, lon}])
 * @param base    {lat, lon} | null
 * @returns {coords:[[lon,lat]...], hops:[{nodeId, slot, lat, lon}], unresolved:[nodeId], direct, complete}
 */
export function buildRoute({ hiker, routePath, devices = [], relays = [], base = null }) {
  const empty = { coords: [], hops: [], unresolved: [], direct: false, complete: false };
  if (!hasPos(hiker)) return empty;
  const ids = parseRoute(routePath);
  const slotByNode = new Map(
    devices.filter((d) => d.role === "relay" && d.plan_slot != null).map((d) => [d.node_id, d.plan_slot])
  );
  const relayBySlot = new Map(relays.filter(hasPos).map((r) => [r.n, r]));

  const hops = [];
  const unresolved = [];
  for (const id of ids) {
    const r = relayBySlot.get(slotByNode.get(id));
    if (r) hops.push({ nodeId: id, slot: r.n, lat: r.lat, lon: r.lon });
    else unresolved.push(id);
  }
  const coords = [[hiker.lon, hiker.lat], ...hops.map((h) => [h.lon, h.lat])];
  if (hasPos(base)) coords.push([base.lon, base.lat]);
  return {
    coords: coords.length >= 2 ? coords : [],
    hops,
    unresolved,
    direct: ids.length === 0,
    complete: unresolved.length === 0 && hasPos(base),
  };
}

// Radius Bumi rata-rata (meter). SAMA dengan backend/app/services/geo.py dan SQL geo_dist_m,
// supaya jarak di layar cocok dengan yang dihitung backend. JANGAN pakai 6371.0 km (milik terrain_planner, sedikit beda).
const EARTH_RADIUS_M = 6371008.8;

/**
 * Jarak great-circle (Haversine) antara dua titik dalam meter.
 * KONVENSI lat/lon (bug #1 proyek): tiap titik adalah [lat, lon] (lintang dulu), sama dengan site.trail.
 * @param {[number, number]} a titik [lat, lon]
 * @param {[number, number]} b titik [lat, lon]
 * @returns {number} jarak dalam meter (nilai sungguhan, 0 bila dua titik sama)
 */
export function haversineM([lat1, lon1], [lat2, lon2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(s)));
}

/**
 * Jarak horizontal trail per segmen: base -> titik1 -> titik2 -> ...
 * KONVENSI lat/lon (bug #1 proyek): base = {lat, lon} | null; points = array [lat, lon] (lintang dulu, sama dengan site.trail).
 * Bila base null, mulai dari titik trail pertama. 0 atau 1 titik (tanpa base) -> total 0 dan tidak ada segmen.
 * @param {{lat:number, lon:number}|null} base titik base station
 * @param {Array<[number, number]>} points titik trail [lat, lon]
 * @returns {{ totalM:number, segments:Array<{fromLabel:string, toLabel:string, m:number}> }}
 */
export function trailSegments(base, points = []) {
  const baseOk = !!base && typeof base.lat === "number" && typeof base.lon === "number";
  // Simpul berurutan + label operator: base lalu titik1, titik2, ...
  const nodes = [];
  if (baseOk) nodes.push({ label: "Base", point: [base.lat, base.lon] });
  points.forEach((p, i) => nodes.push({ label: `Titik ${i + 1}`, point: p }));

  const segments = [];
  let totalM = 0;
  for (let i = 1; i < nodes.length; i++) {
    const m = haversineM(nodes[i - 1].point, nodes[i].point);
    totalM += m;
    segments.push({ fromLabel: nodes[i - 1].label, toLabel: nodes[i].label, m });
  }
  return { totalM, segments };
}

/** GeoJSON untuk MapLibre: satu garis rute + titik sorot di tiap relay yang dilewati. */
export function routeFeatureCollection(route) {
  const features = [];
  if (route.coords.length >= 2) {
    features.push({ type: "Feature", properties: { kind: "route" }, geometry: { type: "LineString", coordinates: route.coords } });
  }
  for (const h of route.hops) {
    features.push({ type: "Feature", properties: { kind: "hop", slot: h.slot }, geometry: { type: "Point", coordinates: [h.lon, h.lat] } });
  }
  return { type: "FeatureCollection", features };
}

/** Pesan untuk operator bila ada relay di rute yang belum dipetakan; "" bila tidak ada masalah. */
export function unresolvedMessage(route) {
  if (!route.unresolved.length) return "";
  const names = route.unresolved.map((n) => `R${n}`).join(", ");
  return `Relay ${names} belum dipetakan ke posisi (tab Perangkat), jadi tidak digambar di rute.`;
}
