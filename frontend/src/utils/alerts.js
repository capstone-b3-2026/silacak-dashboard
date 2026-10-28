// Nama alarm yang mudah dibaca operator (dipakai SosOverlay dan MonitoringPanel)
const LABELS = {
  STAGNANT: "diam di tempat",
  MANUAL_SOS: "SOS manual",
  LOW_BATTERY: "baterai kritis",
  OFF_TRAIL: "di luar jalur",
};

export function alertLabel(type) {
  const t = LABELS[type] || type?.toLowerCase() || "tidak diketahui";
  return t.charAt(0).toUpperCase() + t.slice(1);
}
