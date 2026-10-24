const BASE_URL = "/api/v1";

export async function fetchLatestPositions() {
  const res = await fetch(`${BASE_URL}/positions/latest`);
  return res.json();
}

export async function fetchHikerTrack(hikerCode) {
  const res = await fetch(`${BASE_URL}/positions/${hikerCode}/track`);
  return res.json();
}

export async function fetchAlerts() {
  const res = await fetch(`${BASE_URL}/alerts`);
  return res.json();
}

export async function acknowledgeAlert(alertId) {
  return fetch(`${BASE_URL}/alerts/${alertId}/acknowledge`, { method: "POST" });
}

export function gpxDownloadUrl(hikerCode) {
  return `${BASE_URL}/gpx/${hikerCode}`;
}

// ── Setup lokasi / DEM / relay ──
async function jsonOrThrow(res) {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Error ${res.status}`);
  return body;
}

export async function fetchActiveSite() {
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/active`));
}

export async function dismissFailedUpload() {
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/pending`, { method: "DELETE" }));
}

export async function uploadDem(file, name) {
  const fd = new FormData();
  fd.append("name", name);
  fd.append("file", file);
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/dem`, { method: "POST", body: fd }));
}

export async function saveSiteInputs(payload) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/sites/active/inputs`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function computeRelayPlan() {
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/active/plan`, { method: "POST" }));
}

export async function uploadCanopy(file) {
  const fd = new FormData();
  fd.append("file", file);
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/active/canopy`, { method: "POST", body: fd }));
}

export async function deleteCanopy() {
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/active/canopy`, { method: "DELETE" }));
}

export async function fetchCalibration({ sessionId = null, hours = 72, maxKm = null } = {}) {
  const q = new URLSearchParams({ hours: String(hours) });
  if (sessionId != null) q.set("session_id", String(sessionId));
  if (maxKm != null) q.set("max_km", String(maxKm));
  return jsonOrThrow(await fetch(`${BASE_URL}/sites/active/calibration?${q}`));
}

export const planGpxUrl = `${BASE_URL}/sites/active/plan.gpx`;

// ── Perangkat LoRa ──
export async function fetchDevices() {
  return jsonOrThrow(await fetch(`${BASE_URL}/devices`));
}
export async function createDevice(d) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/devices`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) })
  );
}
export async function updateDevice(id, d) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/devices/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) })
  );
}
// Petakan relay ke posisi R<n> pada rencana lokasi (null = lepas). Data dashboard saja, tidak dikirim ke alat.
export async function setDevicePlanSlot(id, planSlot) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/devices/${id}/plan-slot`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan_slot: planSlot }),
    })
  );
}
export async function deleteDevice(id) {
  return jsonOrThrow(await fetch(`${BASE_URL}/devices/${id}`, { method: "DELETE" }));
}
export async function pushDevice(id) {
  return jsonOrThrow(await fetch(`${BASE_URL}/devices/${id}/push`, { method: "POST" }));
}

// -- Sesi pendakian (check-in / check-out / riwayat) --
export async function fetchHikers() {
  return jsonOrThrow(await fetch(`${BASE_URL}/hikers`));
}

export async function fetchSessions(status = "active") {
  return jsonOrThrow(await fetch(`${BASE_URL}/sessions?status=${status}`));
}

export async function checkInSession(payload) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function checkOutSession(sessionId) {
  return jsonOrThrow(await fetch(`${BASE_URL}/sessions/${sessionId}/checkout`, { method: "POST" }));
}

export function sessionGpxUrl(sessionId) {
  return `${BASE_URL}/gpx/session/${sessionId}`;
}

// -- Geser relay manual (Setup aktif): kirim posisi semua relay urut R1..Rn, backend menilai ulang tiap link dari DEM --
export async function saveRelayPositions(relays) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/sites/active/relays`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relays }),
    })
  );
}

// ── Diagnostik link ──
export async function fetchDiagnostics() {
  return jsonOrThrow(await fetch(`${BASE_URL}/diagnostics`));
}

export async function fetchPackets(hikerCode, limit = 300) {
  return jsonOrThrow(await fetch(`${BASE_URL}/diagnostics/${hikerCode}/packets?limit=${limit}`));
}

// ── Status base station (backend sudah punya, dipakai lencana di dashboard) ──
export async function fetchBaseStatus() {
  return jsonOrThrow(await fetch(`${BASE_URL}/base/status`));
}
export async function fetchBasePorts() {
  return jsonOrThrow(await fetch(`${BASE_URL}/base/ports`));
}
export async function selectBasePort(port) {
  return jsonOrThrow(
    await fetch(`${BASE_URL}/base/port`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ port }) })
  );
}

// ── Ekspor CSV, cadangan, folder data ──
export function sessionCsvUrl(sessionId) {
  return `${BASE_URL}/export/session/${sessionId}.csv`;
}
// from / to: ISO string atau kosong (kosong = tanpa batas)
export function rangeCsvUrl(from, to) {
  const q = new URLSearchParams();
  if (from) q.set("from", from);
  if (to) q.set("to", to);
  const s = q.toString();
  return `${BASE_URL}/export/positions.csv${s ? `?${s}` : ""}`;
}
export const backupZipUrl = `${BASE_URL}/export/backup.zip`;
export async function fetchDataInfo() {
  return jsonOrThrow(await fetch(`${BASE_URL}/export/data-info`));
}
export async function openDataFolder() {
  return jsonOrThrow(await fetch(`${BASE_URL}/export/open-data-folder`, { method: "POST" }));
}
