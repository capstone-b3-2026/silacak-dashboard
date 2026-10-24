"""Pemicu SiLacak.exe: hanya menjalankan Python bawaan paket dengan launcher.

Sengaja sangat kecil (tanpa dependensi) supaya PyInstaller membekukannya tanpa masalah hidden import:
semua pustaka berat (FastAPI, rasterio, dst.) tetap Python biasa di folder python\\ dengan versi yang sama
seperti saat dikembangkan. Layout paket:

    SiLacak.exe   <- file ini (dibekukan)
    python\\       Python embeddable + site-packages
    launcher\\     silacak_launcher.py, pgmanager.py
    backend\\  frontend\\  pgsql\\
"""
import os
import subprocess
import sys


def main(base: str | None = None) -> int:
    if base is None:
        base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    py = os.path.join(base, "python", "python.exe" if os.name == "nt" else "python")
    script = os.path.join(base, "launcher", "silacak_launcher.py")
    if not (os.path.exists(py) and os.path.exists(script)):
        print("Paket SiLacak tidak lengkap (folder 'python' atau 'launcher' hilang). Unduh dan ekstrak ulang paket lengkapnya.")
        input("\nTekan Enter untuk menutup...")
        return 1
    env = dict(os.environ)
    for var in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):  # jangan terpengaruh Python lain di laptop ini
        env.pop(var, None)
    proc = subprocess.Popen([py, script], cwd=base, env=env)
    while True:
        try:
            rc = proc.wait()
            break
        except KeyboardInterrupt:
            # Ctrl+C juga diterima proses anak, yang sedang mematikan Postgres dengan rapi. Pemicu tidak boleh
            # keluar lebih dulu (konsol kembali ke prompt padahal shutdown belum selesai); tunggu saja.
            continue
    if rc != 0:  # tanpa ini jendela hitam langsung hilang dan pesan error tidak sempat terbaca
        input(f"\nSiLacak berhenti (kode {rc}). Tekan Enter untuk menutup...")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
