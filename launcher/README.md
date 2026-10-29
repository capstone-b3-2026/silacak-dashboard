# Launcher SiLacak (mode portable, tanpa Docker)

Tujuan: operator basecamp yang tidak teknis cukup **extract zip lalu klik `SiLacak.exe`**. Database naik sendiri,
dashboard terbuka di browser, base station dikenali otomatis. Tanpa Docker, Node, nginx, atau file `.env`.

## Yang dilakukan `SiLacak.exe`
1. Membuat config sekali (`%LOCALAPPDATA%\SiLacak\config.json`: port bebas + password database acak).
2. Menyiapkan klaster PostgreSQL portable di `%LOCALAPPDATA%\SiLacak\pgdata` (hanya `127.0.0.1`), lalu membuat database.
3. Pertama kali: membuka wizard `/awal`. "Tidak" atau "Tidak tahu" memakai nilai bawaan (dari `backend/app/core/config.py`, dijaga
   sama dengan `backend/.env.example` oleh tes); "Ya" membuka formulir berlabel bahasa biasa (parameter alarm stagnan, pilihan port base).
   Pilihan disimpan di `data\app_settings.json` dan langsung berlaku tanpa restart; bisa diubah lagi di `http://127.0.0.1:<port>/pengaturan`.
   Menutup wizard tanpa menjawab tidak memblokir apa pun.
4. Menjalankan backend yang sekaligus menyajikan dashboard dan membaca USB serial base station (`SERIAL_PORT=auto`).
5. Membuka jendela dashboard (Edge `--app --start-fullscreen` bila ada, jika tidak browser bawaan). Mode layar penuh menyembunyikan title bar agar terasa seperti aplikasi native; operator tetap bisa keluar dengan F11 atau menutup dengan Alt+F4. Ikon jendela/taskbar memakai logo aplikasi (favicon di `frontend/index.html`).
6. Saat ditutup: menghentikan database dengan rapi. Kalau jendela ditutup paksa, peluncuran berikutnya memakai ulang database yang masih hidup.

Data pengguna (database, DEM/tile, log mentah serial `data\raw\`) ada di `%LOCALAPPDATA%\SiLacak`, terpisah dari folder program.
Server hanya mendengarkan `127.0.0.1`, jadi tidak ada popup firewall dan tidak terbuka ke jaringan.

## Layout paket (hasil build)
```
SiLacak\
  SiLacak.exe        launcher + backend (PyInstaller onedir; folder _internal ikut)
  frontend\          hasil `npm run build`
  pgsql\bin\...      PostgreSQL 16 portable (initdb, pg_ctl, createdb, postgres)
  samples\           (opsional) DEM contoh
```

## Menjalankan dari source (untuk pengembangan, Linux/macOS/Windows)
```
# butuh PostgreSQL 16 di PATH (atau set SILACAK_PG_BIN) dan frontend sudah di-build ke frontend/dist
pip install -r backend/requirements.txt
python launcher/silacak_launcher.py
```
Data dev ada di `$SILACAK_HOME` (bawaan: `~/.local/share/silacak`).

## Build paket Windows
**Disarankan: `build_portable.ps1`** (Python bawaan). Paket berisi Python embeddable + pustaka yang dipasang dengan pip (versi sama dengan
saat dikembangkan), ditambah `SiLacak.exe` kecil yang hanya menjalankan launcher. Tidak ada proses "membekukan" aplikasi, jadi tidak ada
masalah hidden import yang baru ketahuan saat fitur tertentu dipakai (mis. unggah DEM), dan lebih jarang ditandai antivirus. Skrip ini
mengakhiri dengan uji impor semua pustaka berat, supaya yang kurang ketahuan saat build, bukan di laptop operator.
```
powershell -ExecutionPolicy Bypass -File launcher\build_portable.ps1
```
Hasil: `launcher\dist\SiLacak-windows.zip`. Uji dengan mengekstraknya ke folder BARU, lalu klik `SiLacak.exe`.

Cadangan: `build_windows.ps1` (PyInstaller penuh; spec `silacak.spec`). Binary PostgreSQL portable diletakkan manual di `launcher/third_party/pgsql`
(tidak dimasukkan ke repo). Tidak perlu PostGIS maupun TimescaleDB.

## Installer .exe (Inno Setup) -- T-27
Agar operator cukup "unduh satu `.exe`, klik, pilih folder, selesai" (bukan ekstrak zip), paket portable di atas dibungkus menjadi
`SiLacak-Setup.exe` dengan Inno Setup. Skripnya `launcher\silacak_installer.iss`.

Sifat installer:
- Per-user (`PrivilegesRequired=lowest`): tidak butuh hak admin; default folder `%LOCALAPPDATA%\Programs\SiLacak`, tetapi pengguna boleh memilih folder lain.
- Opsi centang "Buat pintasan di Desktop" dan pintasan Start Menu.
- Uninstaller dengan ikon aplikasi (`frontend\public\LOGO.ico`).
- **Tidak memuat `.env`** (mode portable memakai `config.json` di `%LOCALAPPDATA%\SiLacak`).
- Uninstaller **tidak** menghapus data operator di `%LOCALAPPDATA%\SiLacak` (database, DEM, pengaturan); hanya berkas program yang dibuang. Install ulang tetap melihat data lama.

Prasyarat build: **Inno Setup 6** terpasang (`ISCC.exe`, unduh gratis dari <https://jrsoftware.org/isdl.php>). `build_portable.ps1` memanggil `ISCC.exe` otomatis pada langkah 8/8 bila ditemukan; bila tidak terpasang, pembuatan installer dilewati dengan peringatan dan zip portable tetap dihasilkan. Membuat installer secara manual:
```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" launcher\silacak_installer.iss
```
Hasil: `launcher\dist\SiLacak-Setup.exe`. Uji round trip di Windows bersih: jalankan installer -> `SiLacak.exe` jalan -> uninstall -> pastikan folder program bersih dan `%LOCALAPPDATA%\SiLacak` tetap ada.

Tingkat bukti: skrip ditulis (T1). Build dan uji installer hanya bisa dilakukan di Windows (T2/T3) oleh pemilik.

## Status pengujian (jujur)
Teruji otomatis (`python -m unittest discover -s launcher/tests`): config, pemilihan port, perintah initdb/pg_ctl/createdb
dengan proses di-fake. **Belum pernah dijalankan**: initdb/pg_ctl asli, build PyInstaller (hidden import rasterio/uvicorn/asyncpg
kemungkinan perlu disesuaikan), perilaku di Windows (termasuk akun Administrator, antivirus, SmartScreen untuk exe tanpa tanda tangan).
Build harus dilakukan di Windows (PyInstaller tidak lintas-OS); rencananya lewat GitHub Actions `windows-latest`.

## Tes tanpa hardware: base station palsu
`backend/scripts/fake_base.py` meniru base station lewat soket TCP (format `CSV_DATA` persis firmware, termasuk paket tanpa fix
dan paket hilang). Backend membukanya seperti port serial (`socket://127.0.0.1:7777`), jadi pembaca serial, parser, INSERT, dan
auto-reconnect ikut teruji. Tidak teruji: kabel USB, driver CH340/CP210x, dan radio LoRa. Langkahnya ada di docstring skrip itu.

## Belum ada (Fase 2/3)
Tombol "Pengaturan" di dalam dashboard Vue (sekarang hanya lewat alamat /pengaturan), ekspor/impor "paket lokasi", ikon tray, bundel driver USB (CP210x/CH340),
pipeline rilis, penanganan SmartScreen. (Installer `.exe` sudah ada skripnya -- lihat bagian "Installer .exe" di atas -- tetapi belum diuji build/round trip di Windows.)
