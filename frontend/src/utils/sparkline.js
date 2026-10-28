// Logika murni untuk crosshair sparkline (tanpa browser/Vue).
// Konvensi posisi x mengikuti spark(): titik ke-i digambar pada x = (i/(n-1))*W,
// jadi tepi kiri grafik = index 0 dan tepi kanan = index n-1 (tanpa padding horizontal).

// Dari rasio x (0..1 relatif lebar grafik) dan jumlah titik n, kembalikan index titik
// data TERDEKAT (snap, bukan posisi bebas). Pembulatan ke terdekat, lalu di-clamp ke [0, n-1].
// Kasus aman: n <= 0 -> 0 (pemanggil tetap harus cek data kosong sebelum menggambar),
// n === 1 -> 0 (hanya satu titik). Fungsi tidak pernah melempar.
export function nearestIndexFromRatio(ratio, n) {
  if (!Number.isFinite(n) || n <= 1) return 0;
  const r = Number.isFinite(ratio) ? ratio : 0;
  const idx = Math.round(r * (n - 1));
  return Math.max(0, Math.min(n - 1, idx));
}
