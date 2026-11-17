# SiLacak Dashboard

Dashboard monitoring lokasi pendaki untuk area tanpa sinyal seluler. Sistem ini menerima data dari base station LoRa lewat port serial USB, menyimpannya, lalu menampilkannya kepada petugas basecamp pada peta, lengkap dengan diagnostik kualitas tautan. Seluruh layanan berjalan lokal di satu laptop atau mini-PC, tanpa internet.

Dokumen ini hanya membahas bagian perangkat lunak (dashboard, backend, basis data, dan bridge serial). Perangkat keras dan firmware dikerjakan tim lain.

<!-- Tambahkan tangkapan layar dashboard di sini: ![Dashboard](docs/dashboard.png) -->

## Daftar Isi

1. [Status](#status)
2. [Fitur](#fitur)
3. [Perbedaan dengan C-251 dan Alasannya](#perbedaan-dengan-c-251-dan-alasannya)
4. [Alur Data dan Stack](#alur-data-dan-stack)
5. [Menjalankan](#menjalankan)
6. [Cara Penggunaan](#cara-penggunaan)
7. [Menghubungkan Base Station](#menghubungkan-base-station)
8. [Mengakses Basis Data](#mengakses-basis-data)
9. [Push Konfigurasi ke Perangkat](#push-konfigurasi-ke-perangkat)
10. [Diagnostik Tautan: Definisi dan Batasan](#diagnostik-tautan-definisi-dan-batasan)
11. [Konfigurasi](#konfigurasi)
12. [Data Sintetis](#data-sintetis-pengembangan)
13. [Struktur Folder dan API](#struktur-folder)
14. [Keamanan](#keamanan)
15. [Batasan yang Diketahui](#batasan-yang-diketahui)
16. [Langkah Selanjutnya](#langkah-selanjutnya)
17. [Pemecahan Masalah](#pemecahan-masalah)
18. [Catatan Teknis](#catatan-teknis)

## Status

| Hal | Status |
|---|---|
| Dashboard, backend, basis data, bridge serial | Diimplementasikan |
| Pengujian otomatis | Belum ada |
| Pengujian end-to-end dengan hardware nyata | Belum didokumentasikan sebagai selesai |
| Relay node dan pengujian multi-hop | Belum ada (relay belum dibangun) |
| Tombol SOS manual, data baterai, SNR | Belum tersedia pada paket data dari firmware |
| Penggunaan di jaringan terbuka | Tidak disarankan (lihat bagian Keamanan) |

## Fitur

- Peta 2D dan 3D (MapLibre GL) dengan peta dasar topo offline yang dibangkitkan dari DEM, serta OpenStreetMap online sebagai opsi tambahan.
- Railing koridor di sekitar jalur: dua garis putus-putus (pagar kiri dan kanan) pada jarak `stagnant_perimeter_m` dari garis jalur (bawaan 50 m; ikut berubah begitu operator mengubahnya di pengaturan, dan legenda peta menampilkan angkanya), selalu tampil begitu jalur punya minimal dua titik, sebagai penanda visual perimeter deteksi stagnan. Warnanya amber pudar (bukan merah) karena merah hanya untuk SOS, dan diletakkan di bawah marker.
- Marker posisi, jejak per sesi, dan popup per pendaki. Bila paket terbaru tidak punya GPS fix, marker tetap di lokasi fix terakhir dan diberi lencana "gps invalid".
- Sesi pendakian (check-in dan check-out) per perangkat, dengan data pendaki dan kontak darurat. Satu perangkat hanya boleh punya satu sesi aktif.
- Alarm "stagnan" otomatis bila pendaki berada dalam radius tertentu selama jendela waktu tertentu. Jendela waktu bergantung pada posisi terakhir pendaki terhadap koridor (perimeter) di sekitar jalur: bila masih di dalam koridor (dianggap istirahat atau tidur) jendela panjang, bila sudah menyimpang keluar koridor (dianggap lebih mungkin kecelakaan) jendela pendek. Bila lokasi aktif belum punya jalur (kurang dari dua titik), deteksi stagnan tidak berjalan. Alarm dapat di-acknowledge dari dashboard dan memicu overlay bersuara.
- Peringatan dini "di luar jalur" (OFF_TRAIL): bila posisi terakhir pendaki aktif keluar dari koridor perimeter (memakai `stagnant_perimeter_m` yang sama dengan deteksi stagnan, bawaan 50 m) selama beberapa paket berfix berturut-turut (bawaan tiga, `OFFTRAIL_DEBOUNCE_PACKETS`) (debounce untuk menapis lonjakan GPS), dashboard menampilkan peringatan di daftar alarm dan lencana pada kartu pendaki. Peringatan ini berwarna amber (bukan merah, karena merah hanya untuk SOS), TIDAK dapat disenyapkan manual, dan hilang OTOMATIS begitu pendaki kembali masuk perimeter. Sinyal ini TERPISAH dari dan tidak menggantikan Auto-SOS stagnan maupun SOS manual; ia hanya menarik perhatian operator lebih awal. Bila lokasi aktif belum punya jalur (kurang dari dua titik), deteksi ini dilewati. Deteksi berjalan pada callback NOTIFY per paket sehingga peringatan muncul dalam satu-dua paket. Tingkat bukti: T1 (fungsi murni `geo.is_off_trail` dan layanan `off_trail_watch` teruji unit, build frontend lolos); T2 ke atas (Postgres sungguhan, paket nyata, hardware) belum. Ambang perimeter 50 m dan debounce 3 paket adalah asumsi yang belum dikalibrasi lapangan.
- Diagnostik tautan per sesi aktif: PDR, latensi, status GPS, jarak ke base, status node basi, dan packet log.
- Grafik RSSI terhadap jarak ke base untuk paket langsung (0 hop), dengan estimasi eksponen redaman lintasan n dan simpangan baku shadowing sigma.
- Halaman Setup: unggah DEM GeoTIFF, tentukan posisi base dan jalur, jalankan perencana penempatan relay (pencarian optimal berbasis redaman difraksi pada DEM), geser posisi relay secara manual, dan ekspor rencana ke GPX. Status cakupan relay (tombol "Hitung relay" dan ringkasan "trail tercover" atau jumlah titik belum tercover beserta jumlah relay) kini juga tampil langsung di bagian base dan jalur, tanpa harus menggulir ke panel perencana. Operator juga bisa menaruh, menggeser, dan menghapus relay sendiri di peta, termasuk memilih tanpa relay; saran perencana bersifat opsional.
- Jarak jalur pendakian: jarak horizontal (great-circle Haversine, radius 6371008,8 m konsisten dengan `geo_dist_m`) dihitung instan di peramban begitu base dan minimal dua titik trail ada, lengkap dengan rincian per-segmen. Angka profil 3D (naik-turun sepanjang jalur dari DEM) ditambahkan sebagai angka sekunder setelah DEM siap; segmen di luar cakupan DEM ditandai "sebagian jalur di luar cakupan DEM" (warna amber) dan tidak mengarang elevasi.
- Ekspor jejak sesi ke GPX.
- Manajemen perangkat (Node ID, peran, nama, dan pemetaan relay ke posisi R<n>). Antrean konfigurasi radio ke bridge sudah ada di backend, tetapi dimatikan di UI sampai firmware mendukung `CFG`.

## Perbedaan dengan C-251 dan Alasannya

Prinsip yang dipakai: setiap perubahan terhadap C-251 harus bisa dibela dengan bukti yang dapat diperiksa (persyaratan C-251 sendiri, datasheet atau literatur, atau artefak kode). Hal yang belum memenuhi spesifikasi C-251 tidak dibela sebagai perubahan. Hal itu dicatat apa adanya sebagai kesenjangan beserta rencana penutupannya.

Nomor subbab C-251 di bawah dirujuk dari draf C-601. Cocokkan dengan dokumen C-251 sebelum dikutip di dokumen resmi.

### Yang dipertahankan dari C-251

| Aspek | Keputusan C-251 | Status |
|---|---|---|
| Teknologi komunikasi | LoRa, modul E220-900T22D | Dipakai |
| Topologi | Hybrid direct-mesh | Tautan langsung dipakai, relay belum dibangun |
| Penentuan posisi | GPS NEO-6M, fix valid bila jumlah satelit minimal 4 dan HDOP paling besar 5 | Dipakai, validitas dihitung di bridge |
| Strategi relay | Berdasarkan elevasi dan area tanpa sinyal | Diwujudkan oleh perencana pada DEM nyata |
| Catu daya relay | Panel surya, baterai, MPPT | Ranah tim hardware, di luar dashboard |

### Yang berubah dan alasannya

| ID | Aspek | C-251 | Implementasi sekarang | Alasan dan bukti |
|---|---|---|---|---|
| P01 | Basis data | SQLite pada single-board computer, 3 tabel (Subbab 2.7.3) | PostgreSQL biasa di laptop basecamp (Docker untuk profil server, binary portable untuk profil basecamp). TimescaleDB opsional, PostGIS tidak dipakai | Jarak dihitung Haversine (fungsi SQL `geo_dist_m`, sesuai Subbab 2.6.3) dari kolom bertipe `point`; selisih terhadap spheroid kurang dari sekitar 0,5 persen. Penyampaian data tanpa polling memakai `LISTEN/NOTIFY` yang tidak dimiliki SQLite. RAB C-251 menyebut laptop basecamp sudah tersedia dan tidak membeli SBC. Tetap sepenuhnya lokal tanpa internet. TimescaleDB hanya dipasang bila tersedia (kompresi dan retensi untuk profil server); fitur dashboard tidak bergantung padanya. Bukti: `schema.py`, `find_stagnant_sessions` di `position_repo.py`. |
| P02 | Peta | Leaflet dengan OpenStreetMap (Subbab 2.7.2) | MapLibre GL 2D dan 3D, peta topo offline dari DEM, OSM sebagai opsi | C-251 menetapkan bahwa LOS atau NLOS ditentukan oleh relief, jadi petugas yang menilai tautan perlu melihat relief. Ubin topo dibangkitkan dari DEM yang sama dengan perencana, sehingga basecamp tidak bergantung pada penyedia ubin. Fungsi inti (marker, polyline jejak, popup) tetap ada. Bukti: `MapView.vue`, `dem_ingest.py`. |
| P03 | Real-time | WebSocket dua arah, target pembaruan 60 detik (Subbab 2.7.1) | SSE melalui `pg_notify`, aksi pengguna lewat REST | Satu-satunya aliran kontinu adalah dari server ke klien. Aksi klien (check-in, setup) bersifat diskret. `EventSource` menyambung ulang otomatis. Target 60 detik tidak bergantung pada protokol karena interval lapor 30 detik jauh lebih besar daripada waktu penerusan di jaringan lokal. Batas: SSE satu arah dan peramban membatasi sekitar enam koneksi per origin. |
| P04 | Skema paket | Payload konseptual: ID, koordinat, timestamp, baterai, RSSI, SNR, SOS | 18 field `CSV_DATA` dari firmware nyata | Ditambahkan nomor urut, rute dan jumlah hop, kecepatan, satelit, HDOP, penanda GPS, penghitung paket hilang, dan waktu GPS. Semuanya dibutuhkan oleh kriteria C-251 sendiri (validitas GPS, membedakan paket langsung dan relay, PDR, latensi). Baterai, SNR, dan SOS tidak ada pada firmware saat ini. Itu kesenjangan, bukan perubahan yang dibela. |
| P05 | PDR | Diterima dibagi dikirim (Subbab 2.5.1) | Dihitung dari penghitung paket hilang berbasis nomor urut, paket pertama sebagai jangkar | Base station tidak dapat menghitung paket yang tidak pernah sampai. Penomoran urut adalah satu-satunya cara menaksir jumlah terkirim pada tautan tanpa acknowledgement. Paket tanpa GPS fix tetap disimpan agar kehilangan tidak lenyap dari penyebut. Batas: taksiran bias ke atas bila paket terakhir hilang, dan perilaku penghitung saat node reboot belum diverifikasi. |
| P06 | Latensi | Model jumlah Time on Air ditambah waktu proses, hasil simulasi median 753,5 ms (Subbab 4.5) | Diukur: waktu paket tersimpan dikurangi waktu GPS, dilaporkan P50 dan P95 | Terukur langsung dari data nyata tanpa instrumen tambahan. Besaran ini mencakup juga waktu tunggu dan pemrosesan, jadi merupakan batas atas bagi latensi tautan: bila lolos 15 detik, spesifikasi lolos. Tidak dibandingkan langsung dengan 753,5 ms karena besarannya berbeda. Batas: butuh jam laptop sinkron. |
| P07 | Perencana relay | Simulasi pada terrain sintetis | Perencana pada DEM GeoTIFF nyata: jalur dirapatkan tiap 40 m, kelayakan tautan memakai redaman difraksi knife-edge (dB), pencarian optimal (jumlah relay minimum lalu biaya terendah), anggaran daya tautan, vegetasi dari raster kanopi opsional, kalibrasi dari RSSI lapangan, posisi dapat digeser manual | C-251 sendiri menyatakan terrain sintetis sebagai keterbatasan dan menjadwalkan data nyata pada Capstone 2. Hasil jujur: bila macet, perencana melaporkan alasannya (`stall_reason`) dan tidak memaksakan relay. Batas: angka mutlak RSSI baru bermakna setelah dikalibrasi, dan vegetasi hanya dihitung bila raster kanopi diunggah. |
| P08 | Sesi pendakian | Tanpa identitas pendaki | Check-in dan check-out per perangkat, satu sesi aktif per perangkat | Portable node dipinjamkan berulang. Tanpa sesi, jejak dua perjalanan bercampur sehingga deteksi diam dan GPX menjadi salah. Tim SAR membutuhkan koordinat yang terkait orang yang bisa dihubungi. Batas: menyimpan data pribadi dan belum ada autentikasi. |
| P09 | Alarm otomatis | Alarm darurat hanya dari tombol SOS manual | Ditambah alarm stagnan otomatis dengan jendela waktu bergantung perimeter jalur | Argumen C-251 terhadap radio HT (korban harus sadar) berlaku sama terhadap tombol manual. Radius bawaan 50 m dipilih sebagai dua kali batas galat GPS vegetasi C-251 (25 m). Jendela waktu dibuat dua tingkat: bila posisi terakhir pendaki masih di dalam koridor (perimeter bawaan 50 m dari garis jalur), diam dianggap wajar (istirahat atau tidur) sehingga jendela panjang (bawaan 480 menit, sekitar 8 jam); bila sudah menyimpang keluar koridor, diam lebih mungkin kecelakaan sehingga jendela pendek (bawaan 240 menit, 4 jam). Bila lokasi aktif belum punya jalur (kurang dari dua titik), deteksi stagnan tidak dijalankan; jalur SOS manual dari hardware (`sos_watch.py`) terpisah dan tidak terpengaruh. Itu penalaran awal yang masuk akal, tetapi belum divalidasi dengan data lapangan. Batas: pendaki yang beristirahat panjang di dalam koridor tetap bisa memicu alarm, artinya "perlu dicek" bukan "darurat pasti". Perimeter 50 m dan kedua jendela adalah ASUMSI BELUM DIKALIBRASI; ketiganya dapat diubah lewat env (`STAGNANT_PERIMETER_M`, `STAGNANT_WINDOW_INSIDE_MINUTES`, `STAGNANT_WINDOW_OUTSIDE_MINUTES`). |
| P10 | Kalibrasi propagasi | Dijadwalkan sebagai agenda Capstone 2 (Subbab 11.2) | Panel RSSI terhadap jarak dengan estimasi n dan sigma | Menjalankan agenda tersebut. Hanya paket langsung, karena RSSI adalah besaran per tautan. Batas: syarat minimum titik bukan jaminan keandalan statistik, dan n cenderung ditaksir terlalu kecil akibat galat jarak GPS. |
| P11 | Konfigurasi perangkat | Tidak ada mekanisme mengubah parameter setelah fabrikasi | Antrean konfigurasi dari dashboard ke base lewat bridge, validasi air data rate (salah satu dari 2,4 / 4,8 / 9,6 / 19,2 / 38,4 / 62,5 kbps) | Duty cycle dinamis dan laju data adalah parameter kendali di C-251, dan mengubahnya tanpa memprogram ulang node dibutuhkan di lapangan. Modul E220 (chip LLCC68) tidak mengekspos SF, bandwidth, dan coding rate secara terpisah, hanya satu setelan air data rate gabungan, jadi dashboard memvalidasi enam nilai kbps itu, bukan angka SF. Batas: dukungan firmware belum ada (lihat bagian Push Konfigurasi). |
| P12 | Ekspor GPX | Integrasi platform eksternal di luar lingkup | Ekspor jejak sesi dan rencana relay ke berkas GPX | GPX adalah format tukar standar untuk perangkat navigasi dan aplikasi peta. Ekspor berkas membawa koordinat ke alur kerja SAR tanpa integrasi online yang dikecualikan C-251. |
| P13 | Node basi | Indikator status komunikasi tiap node | Ditandai "tidak terdengar" bila tidak ada paket lebih dari 120 detik | Empat kali interval lapor. Bila kehilangan paket saling bebas dan PDR 80 persen, empat paket beruntun hilang berpeluang 0,16 persen, jadi alarm palsu jarang tetapi tetap cepat. Batas: kehilangan paket nyata cenderung beruntun, jadi asumsi bebas belum terverifikasi. |
| P14 | Peringatan dini menyimpang | Tidak ada; hanya tombol SOS manual (Subbab 2.5) | Peringatan "di luar jalur" (OFF_TRAIL) saat posisi terakhir keluar koridor perimeter selama beberapa paket berfix berturut-turut (bawaan tiga, dapat diatur) | Deteksi diam (P09) baru menyala setelah jendela waktu panjang; pendaki yang menyimpang jalur dapat dibantu lebih awal bila operator diberi tahu begitu posisi keluar koridor. Memakai perimeter yang sama (`stagnant_perimeter_m`, bawaan 50 m) dan fungsi jarak yang sama (`geo.dist_point_to_trail_m`), jadi tidak ada ambang baru selain debounce. Warna amber (bukan merah; merah hanya SOS), TIDAK dapat disenyapkan manual, dan hilang otomatis saat kembali masuk perimeter sehingga tidak menumpuk. Terpisah dari P09 dan dari SOS manual; tidak mengubah keduanya. Batas: perimeter 50 m dan debounce 3 paket adalah ASUMSI BELUM DIKALIBRASI (debounce dipilih dari interval lapor firmware sekitar 5 detik, kira-kira 15 detik bukti sebelum memperingatkan). Bila jalur kurang dari dua titik, deteksi dilewati. Tingkat bukti T1 (unit dan build); T2 ke atas belum. |

### Pemetaan ke spesifikasi C-251

Ambang spesifikasi tidak diubah. Kolom terakhir menunjukkan seberapa jauh dashboard dapat mengukurnya.

| No | Spesifikasi | Ambang C-251 | Sumber ukur di dashboard | Status alat ukur |
|---|---|---|---|---|
| 1 | Jangkauan | 1000 m LOS, 300 m NLOS | Jarak ke base dan RSSI per paket | Tersedia (tautan langsung) |
| 2 | PDR | 90 persen LOS, 80 persen NLOS | Penghitung paket hilang | Tersedia, bias ke atas |
| 3 | Latensi | 15 detik (1 hop), 30 detik (2 hop) | Umur data, P50 dan P95 | Tersedia, 2 hop belum |
| 4 | Akurasi GPS | 10 m terbuka, 25 m vegetasi | Dihitung offline terhadap titik referensi | Dashboard hanya menampilkan satelit dan HDOP |
| 5 | Pembaruan dashboard | 60 detik | Selisih waktu simpan dan waktu GPS | Sebagian (waktu render di peramban belum dicatat) |
| 6 | Tombol SOS | Tampil dalam 30 detik, 90 persen dari 20 uji | Tidak ada | Tidak tersedia (field SOS belum ada) |
| 7 | Daya relay | Rata-rata sekitar 66 mW, sekitar 7 hari | Tidak ada | Di luar dashboard, baterai tidak terkirim |

## Alur Data dan Stack

1. Portable node mengirim paket LoRa. Base station menerima dan mencetak baris `CSV_DATA` ke USB serial.
2. Bridge Python di komputer host mem-parse baris itu dan menyisipkannya ke PostgreSQL.
3. Trigger basis data menempelkan paket ke sesi aktif dan memanggil `pg_notify`.
4. Backend (FastAPI) menerima notifikasi dan menyiarkannya lewat Server-Sent Events (SSE).
5. Peramban menerima pembaruan lewat `EventSource`. Aksi dari pengguna (check-in, setup, acknowledge) memakai REST.

Bridge berjalan di host, bukan di Docker, karena membutuhkan akses ke port serial.

Pengaturan operator (radius diam, lebar koridor, jendela diam dalam/luar koridor, interval pemeriksaan, dan jumlah paket debounce alarm "di luar jalur") bisa diubah tanpa menyentuh `.env` lewat halaman `/pengaturan` atau tombol Pengaturan (ikon penggeser) di topbar dashboard, yang membuka halaman yang sama di dalam dashboard; garis koridor di peta ikut berubah begitu disimpan. Relay tidak harus menunggu saran perencana: di panel Setup operator bisa menaruh relay sendiri di peta ("Taruh relay di peta"), menggeser, menghapus, atau memilih "Tanpa relay" (0 relay, hanya base); "Saran perencana" tinggal opsional. Batas relay untuk saran otomatis boleh 0 (wizard `/awal` tampil sekali saat pertama kali dijalankan lewat launcher). API-nya `GET/PUT /api/v1/app-config` hanya menerima kunci pada daftar putih dengan batas nilai (`backend/app/services/app_settings.py`); nilai tersimpan di `DATA_DIR/app_settings.json` dan berlaku tanpa restart.

Rute paket nyata digambar di peta untuk pendaki yang dipilih: garis putus-putus terang dari posisi pendaki, lewat relay yang tercatat di `route_path`, sampai base, dengan cincin di tiap relay yang dilewati ("LANGSUNG" = garis lurus ke base). Firmware menulis rute sebagai ID node relay mentah (mis. `R5>R6`), sedangkan koordinat relay ada di rencana lokasi (R1 sampai Rn), jadi tiap perangkat relay harus dipetakan lewat Setup > Perangkat > "Dipasang di posisi" (kolom `devices.plan_slot`, data dashboard saja, tidak dikirim ke alat). Relay yang belum dipetakan dilewati dan diberi tahu lewat pesan di peta. Asumsi yang belum terbukti pada alat: urutan `route_path` = urutan relay dari pendaki ke base. Kode firmware relay (`relay_real.cpp`, relay menambahkan ID-nya sendiri saat meneruskan) mendukung urutan itu, tetapi relay fisik belum dibangun dan diuji; bila terbalik, cukup membalik urutan di `utils/routeGeo.js`. Jika rencana relay dihitung ulang, nomor R<n> bisa bergeser: periksa kembali pemetaannya. Tes logika: `node frontend/src/utils/routeGeo.test.mjs`.

Alternatif tanpa bridge terpisah: backend dapat membaca serial sendiri (`SERIAL_PORT=auto` atau nama port, lihat `backend/.env.example`). Port ESP32 ditemukan otomatis, koneksi pulih sendiri bila kabel dicabut, status ada di `GET /api/v1/base/status`, dan setiap baris `CSV_DATA` ditulis dulu ke log mentah append-only (`DATA_DIR/raw/YYYY-MM-DD.log`) sebelum masuk basis data. Bawaannya `off` agar tidak bentrok dengan bridge eksternal; jangan jalankan keduanya pada port yang sama. Di Docker Desktop untuk Windows port USB tidak diteruskan ke kontainer, jadi pemakaian ini ditujukan untuk mode portable (`launcher/`).

- Backend: FastAPI, asyncpg (SQL langsung, bukan ORM), APScheduler.
- Basis data: PostgreSQL 16. Koordinat bertipe `point` (x = lon, y = lat), jarak lewat fungsi `geo_dist_m` (Haversine). `positions` menjadi hypertable hanya bila TimescaleDB tersedia (profil server); di profil basecamp berupa tabel biasa.
- Frontend: Vue 3, Vite, Pinia, MapLibre GL JS. Disajikan nginx pada port 8080.
- Real-time: posisi dan alarm lewat SSE yang didorong `pg_notify` (bukan WebSocket). Diagnostik tautan (PDR, latensi, node basi, packet log) di-poll dashboard tiap 5 detik (`App.vue`), karena status "basi" memang perlu dihitung ulang berkala walau tidak ada paket baru.
- Deployment: Docker Compose dengan 3 layanan (`db`, `backend`, `frontend`).

## Menjalankan

Prasyarat: Docker dan Docker Compose. Di Windows disarankan Docker Desktop dengan WSL2. Peramban harus mendukung WebGL.

### Mulai cepat (setelah clone)

```bash
git clone <url-repositori> silacak
cd silacak
cp backend/.env.example backend/.env
docker compose up --build
```

Di PowerShell, ganti baris `cp` dengan `copy backend\.env.example backend\.env`.

Berkas `backend/.env` wajib ada karena `docker-compose.yml` membacanya (`env_file`). Isi bawaan `.env.example` sudah cukup untuk pengembangan lokal. Berkas `.env` tidak ikut Git.

Setelah layanan `db` sehat dan `backend` berjalan:

| Layanan | Alamat |
|---|---|
| Dashboard | http://localhost:8080 |
| API dan dokumentasi Swagger | http://localhost:8000/docs |
| Cek kesehatan | http://localhost:8000/health |

Peta topo offline baru tersedia setelah ada lokasi. Langkah berikutnya:

1. Buka http://localhost:8080, panel Setup, tab "Lokasi dan relay".
2. Unggah `samples/klangon_dem.tif` (DEM contoh yang ikut di repositori). Backend membuat ubin 3D dan peta topo offline, jadi tunggu sampai prosesnya selesai. Bila gagal, pesan alasannya tampil di Setup.
3. Setelah peta topo muncul, lanjut dengan penentuan base dan jalur (bagian Cara Penggunaan, langkah A.3 dan seterusnya), lalu isi data sintetis (bagian Data Sintetis) bila belum ada hardware.

DEM contoh mencakup area sekitar 28 x 28 km, jauh lebih luas daripada anjuran potongan 4 x 4 km di bagian Cara Penggunaan. Prosesnya tetap jalan, hanya lebih lama dan menghasilkan lebih banyak ubin daripada DEM yang dipotong sempit.

### Memuat DEM contoh lewat skrip (opsional)

Untuk demo atau pengujian cepat tanpa membuka peramban, DEM contoh dapat dimuat lewat skrip yang memakai pipeline yang sama persis dengan unggah di Setup:

```bash
docker compose exec backend python scripts/load_sample_site.py
```

Opsi: path GeoTIFF lain sebagai argumen (di dalam container, folder `samples/` ada di `/app/samples/`), `--name` untuk nama lokasi, dan `--force`. Skrip menolak jalan bila sudah ada lokasi siap, karena begitu lokasi baru aktif backend menghapus berkas lokasi lama di `data/sites/`. Tanpa `--force`, tidak ada yang terhapus. Backend harus sudah pernah start supaya tabel `sites` ada.

Bila `docker-compose.yml` baru diperbarui (penambahan volume `samples`), jalankan `docker compose up -d` agar container backend dibuat ulang dengan volume itu.

### Folder `data/` dan `samples/`

Folder `data/` di root proyek dipasang ke container backend dan dipakai untuk menyimpan DEM serta ubin peta hasil unggahan di halaman Setup (`data/sites/<id>/`). Folder ini harus dapat ditulis. Di Linux, folder yang dibuat Docker bisa dimiliki root. Bila unggah DEM gagal karena izin, ubah kepemilikan folder tersebut.

Isi `data/` tidak ikut Git (lihat `.gitignore`), kecuali `data/.gitkeep` yang menjaga folder tetap ada. Alasannya: isinya hasil olahan yang dibuat ulang otomatis dari DEM, ukurannya ratusan megabita, dan hanya berguna bila ada baris lokasi yang cocok di basis data. Basis data tersimpan di volume Docker lokal, jadi menyalin `data/sites/` dari komputer lain tidak memunculkan peta. Pakai unggah di Setup atau skrip di atas.

Folder `samples/` berisi DEM contoh dan ikut Git. Folder ini dipasang read-only di `/app/samples` pada container backend.

Reset basis data dari nol (menghapus semua data):

```bash
docker compose down -v
docker compose up --build
```

Seluruh skema basis data (tabel, fungsi, trigger) dibuat dan dimigrasikan otomatis oleh `backend/app/core/schema.py` setiap backend start, sehingga backend juga jalan di PostgreSQL polos. `infra/postgres/init.sql` hanya menyiapkan ekstensi opsional TimescaleDB untuk Docker. Basis data lama yang masih memakai kolom `geography` dimigrasikan otomatis ke `point` (butuh PostGIS masih terpasang pada basis data itu; jalur ini belum diuji pada basis data sungguhan).

### Mode pengembangan frontend

```bash
docker compose up db backend
cd frontend
npm install
npm run dev
```

Vite berjalan di http://localhost:5173 dan meneruskan `/api` ke http://localhost:8000.

### Memasang lewat installer (Windows)

Untuk dipakai di basecamp tanpa Docker, unduh `SiLacak-Setup.exe` dari halaman Releases repositori ini. Arsip portabel (`SiLacak-windows.zip`) juga tersedia di rilis yang sama.

Unduh lewat terminal, jangan lewat peramban. Windows menandai berkas yang diunduh peramban sebagai "berasal dari internet", dan installer yang belum ditandatangani biasanya ditahan atau diperingatkan oleh SmartScreen dan antivirus. Unduhan lewat terminal tidak diberi tanda itu, sehingga peringatannya umumnya tidak muncul. Itu hanya soal penandaan; installer tetap belum bertanda tangan digital.

Repositori ini privat, jadi `curl` ke alamat rilis akan gagal (404). Pakai GitHub CLI:

```bash
winget install --id GitHub.cli
gh auth login
gh release download --repo capstone-b3-2026/silacak-dashboard --pattern "SiLacak-Setup.exe"
```

Perintah terakhir mengunduh rilis terbaru ke folder saat ini. Untuk versi tertentu, tambahkan nomor tag setelah `download`, mis. `gh release download v0.2.0 --repo ...`. Akun GitHub yang dipakai pada `gh auth login` harus punya akses ke repositori.

Bila `gh` tidak ditemukan setelah dipasang, tutup dan buka ulang terminal. Pada Git Bash (MSYS2/UCRT64) PATH Windows tidak selalu ikut, jadi tambahkan sekali: `echo 'export PATH="$PATH:/c/Program Files/GitHub CLI"' >> ~/.bashrc`, lalu buka terminal baru.

Setelah terunduh, jalankan `SiLacak-Setup.exe` dari folder tempat berkas itu disimpan.

## Cara Penggunaan

### A. Persiapan lokasi (sekali per lokasi uji)

1. Buka dashboard, lalu buka panel Setup dan pilih tab "Lokasi dan relay".
2. Unggah satu berkas DEM GeoTIFF (untuk mencoba, pakai `samples/klangon_dem.tif`). Backend menormalkan ke EPSG:4326, membuat ubin elevasi untuk 3D dan ubin topo offline. DEM tanpa CRS ditolak bila koordinatnya bukan derajat. Setelah selesai, peta dasar topo offline tersedia. Setelah lokasi baru aktif, berkas lokasi sebelumnya di `data/sites/` dihapus (barisnya di basis data tetap sebagai riwayat).
3. Aktifkan mode penempatan base lalu klik titik base station di peta.
4. Aktifkan mode jalur lalu klik titik-titik jalur pendakian di peta. Tersedia tombol undo titik dan hapus trail. Begitu jalur punya minimal dua titik, railing koridor (dua garis putus-putus amber sekitar 50 m dari jalur) muncul di peta sebagai penanda perimeter deteksi stagnan.
5. Pada bagian base dan jalur tersedia baris status relay. Bila rencana belum dihitung dan base serta minimal dua titik jalur sudah ada, tombol "Hitung relay" tampil (menjalankan perencana yang sama dengan panel bagian 3). Bila rencana sudah ada, baris itu menampilkan status cakupan ("trail tercover" atau jumlah titik belum tercover) beserta jumlah relay, sehingga operator tidak perlu menggulir ke panel perencana. Isi parameter perencana bila perlu (buka tombol "Konfigurasi Lanjutan" di bagian bawah panel Setup; arti tiap parameter ada di bagian [Perencana Relay](#perencana-relay)), lalu klik "Simpan dan hitung ulang".
6. Rencana relay dihitung setelah base dan minimal dua titik jalur ada. Bila base langsung menjangkau seluruh jalur, dashboard menyatakan relay tidak diperlukan. Bila perencana macet, pesan alasannya ditampilkan. Selama panel Setup terbuka, penanda relay dapat digeser di peta dan redaman tiap tautan dihitung ulang dari DEM dengan model yang sama dengan perencana. Tombol "Saran perencana" membuang susunan relay yang ada (termasuk yang digeser manual) lalu menghitung ulang dari nol.
7. Rencana relay dapat diekspor ke GPX.

Catatan: frekuensi bawaan perencana adalah 922 MHz, mengikuti pita legal Indonesia 920 sampai 923 MHz (AS923, Permenkominfo 1/2019, sesuai C-251). Nilai 915 MHz sebelumnya adalah pita Amerika Serikat dan tidak patuh. Angka ini hanya parameter model perencana (memengaruhi FSPL dan radius Fresnel), bukan nilai yang dikirim ke alat. Firmware memakai `LORA_CHANNEL 70`; frekuensi MHz aktualnya tercetak di Serial saat boot dan belum dikonfirmasi sama persis dengan 922 MHz. Samakan kanal semua node atau mereka tidak saling mendengar.

**Menyiapkan berkas DEM.**

- Format GeoTIFF satu band, nilai elevasi dalam meter (rentang yang diterima -500 sampai 9000 m). Batas unggah 200 MB (`client_max_body_size` di `frontend/nginx.conf`).
- Potong (clip) sekecil mungkin di sekitar jalur, dengan margin sekitar 1,5 km dari jalur untuk ruang cari relay. Untuk Bukit Klangon, kotak sekitar 4 x 4 km sudah cukup. Area yang lebih luas hanya memperlambat pembuatan ubin dan menambah penyimpanan. Pembuat ubin menurunkan zoom maksimum otomatis bila jumlah ubin melebihi 4.000.
- Contoh dengan GDAL (`-projwin` urutannya barat, utara, timur, selatan): `gdal_translate -projwin W N E S -co COMPRESS=DEFLATE sumber.tif clip.tif`. Di QGIS: Raster, Extraction, Clip Raster by Extent.
- Ukuran piksel bukan resolusi spasial. DEM yang diunduh pada piksel 8 m bisa berasal dari sumber 30 m yang di-resample, sehingga detailnya tidak lebih halus dari sumbernya. Periksa sumber aslinya (Copernicus GLO-30, DEMNAS, dan sebagainya) dan laporkan resolusi sumber, bukan ukuran piksel berkas. Untuk analisis LOS dan Fresnel sejauh 1 sampai 2 km, DEM 30 m cukup menangkap punggungan dan lembah yang menentukan.
- Setelah `docker compose down -v`, catatan lokasi (base, jalur, rencana) di basis data ikut terhapus walau berkas DEM masih ada di `data/sites/`. Kosongkan isi `data/sites/` (agar tidak tersisa ubin lama, karena nomor lokasi dimulai lagi dari 1), lalu unggah ulang DEM di Setup dan tentukan lagi base dan jalur.

### B. Mendaftarkan perangkat

1. Di panel Setup, buka tab "Perangkat".
2. Isi Node ID (sama dengan `node_id` pada firmware, 1 sampai 254), peran (`tracker`, `relay`, atau `base`), dan nama, lalu simpan. Kolom konfigurasi radio dan tombol Push disembunyikan di UI selama firmware belum mendukung `CFG` (lihat bagian Push Konfigurasi).
3. Perangkat berperan `tracker` otomatis dipetakan ke kode pendaki `H01`, `H02`, dan seterusnya sesuai Node ID.

### C. Menyalakan penerimaan data

Colokkan base station ke USB, pastikan layanan Docker berjalan, lalu jalankan bridge (lihat bagian Menghubungkan Base Station). Posisi muncul di peta setiap kali paket diterima.

### D. Check-in pendaki

1. Buka panel "sesi pendakian" (terlipat secara bawaan, klik untuk membuka).
2. Pilih alat dari dropdown (daftar perangkat terdaftar bertipe tracker, mis. "H01 - Tracker Andi"; alat yang sedang dipakai sesi aktif tidak muncul agar tidak dobel). Isi nama pendaki, kontak darurat (opsional), dan jalur (opsional), lalu klik "Mulai sesi". Bila belum ada alat terdaftar, muncul petunjuk untuk menambahkannya di Setup > Perangkat.
3. Bila sebuah alat mengirim data tetapi belum di-check-in, muncul banner "Belum check-in" dengan tautan "isi data". Sesi dibuka otomatis dan ditandai `auto_opened` agar datanya tidak terbuang. Lengkapi datanya dari banner tersebut.

### E. Memantau

Panel monitoring memiliki empat tab:

| Tab | Isi |
|---|---|
| hikers | Daftar pendaki dan detail pendaki terpilih (RSSI, hop, satelit dan HDOP, lencana "gps invalid" dan "tidak terdengar"). |
| links | Ringkasan tautan per pendaki: rute, hop, RSSI, jarak ke base, PDR, latensi P50 dan P95, jumlah paket tanpa fix atau GPS invalid. Klik satu baris untuk memilih pendaki. |
| log | Packet log pendaki terpilih (daftar 60 paket terakhir) dan grafik RSSI terhadap jarak ke base. Grafik dan estimasi n dan sigma memakai hingga 300 paket terakhir sesi itu (batas `fetchPackets`). |
| sos | Daftar alarm aktif dan yang sudah di-acknowledge. |

Kartu "pdr sesi" di panel ringkasan menggabungkan seluruh sesi aktif dengan rumus PDR yang sama. Kartu "latency e2e" menampilkan median dari P50 tiap sesi aktif (dalam detik). Jarak ke base hanya muncul bila titik base sudah di-set di Setup.

### F. Menangani alarm

Alarm baru memunculkan overlay bersuara. Peramban memblokir suara otomatis sebelum ada interaksi, jadi klik satu kali di halaman setelah dibuka agar suara dapat berbunyi. Klik acknowledge setelah ditangani. Ingat bahwa alarm stagnan berarti "perlu dicek".

### G. Check-out dan ekspor

Klik "Check-out" pada sesi aktif untuk menutupnya. Jejak setiap sesi, aktif maupun riwayat, dapat diunduh lewat "Unduh GPX".

### H. Pengambilan data untuk kalibrasi dan uji tautan

1. Pastikan titik base sudah di-set dan jam laptop sinkron (NTP).
2. Check-in perangkat uji, lalu bergerak menjauhi base pada jalur terbuka dengan jarak yang bervariasi.
3. Kumpulkan sesedikit-dikitnya beberapa ratus paket. Sebagai gambaran, agar batas bawah selang kepercayaan Wilson 95 persen untuk PDR melampaui 90 persen saat PDR terukur 95 persen, dibutuhkan sekitar 140 paket.
4. Lihat tab "log": estimasi n dan sigma muncul bila ada minimal 5 titik langsung dengan rentang jarak yang cukup lebar. Angka itu valid hanya untuk lokasi uji. Karena grafik memakai paket 300 terakhir, ambil angka n dan sigma sebelum sesi melewati 300 paket, atau tangkap lewat `GET /api/v1/diagnostics/{kode}/packets?limit=500` bila butuh data lebih panjang.

### Perencana Relay

Perencana mencari posisi dan jumlah relay yang menjangkau **seluruh jalur** dengan relay sesedikit mungkin, lalu memilih yang paling andal. Kode: `backend/app/services/terrain_planner.py` (`suggest_relay_chain`, `evaluate_relay_chain`, `predict_links`). Versi greedy lama masih ada sebagai `*_greedy` untuk pembanding. Kalibrasi dari RSSI lapangan ada di `backend/app/services/link_calibration.py`.

**Model tautan** (semua dalam dB):

```
RSSI prediksi = P_tx + G_a + G_b - FSPL(d, f) - L_medan - L_vegetasi - offset_kalibrasi
margin fading = RSSI prediksi - sensitivitas
tautan layak  = L_medan <= redaman medan maks  DAN  margin fading >= margin fading yang disyaratkan  DAN  d <= hop maks
```

- `FSPL` = 32,44 + 20 log10(d km) + 20 log10(f MHz).
- `L_medan` = redaman difraksi knife-edge (ITU-R P.526) pada rintangan terburuk, dengan medan dinaikkan `cadangan galat DEM`. 0 dB berarti zona Fresnel bebas, sekitar 6 dB berarti garis pandang hanya menyentuh puncak. Sampel dalam 30 m dari kedua ujung tautan tidak dihitung karena DEM tidak menyelesaikan detail setinggi itu. `redaman medan maks` adalah batas kepercayaan model difraksi, bukan anggaran daya.
- `L_vegetasi` = Weissberger (daun penuh, rumus yang sama dengan C-251): 0,45 f^0,284 d untuk d sampai 14 m, 1,33 f^0,284 d^0,588 untuk 14 sampai 400 m (f dalam GHz, d dalam m). `d` adalah panjang bagian garis pandang yang berada **di dalam kanopi**; kedalaman di atas 400 m dijepit. Butuh raster tinggi kanopi (lihat bawah). Tanpa raster, nilainya 0 dan hasil optimistis di hutan.
- `offset_kalibrasi` = redaman tambahan dari hasil kalibrasi RSSI lapangan. Bawaan 0.
- Bawaan P_tx, gain, dan sensitivitas mengikuti C-251 Tabel 10.2 (21 dBm, 5 dBi per antena, -137 dBm untuk SF9). Itu angka **rencana**, bukan hasil ukur.

**Cara mencari:**

1. Jalur dirapatkan menjadi sampel tiap sekitar 40 m. Cakupan dicek di semua sampel, bukan hanya di titik yang diklik.
2. Kandidat relay adalah koridor di sepanjang jalur (jarak ke jalur sampai `radius cari`) pada grid `langkah cari`. Lereng di atas 35 derajat dibuang. Jumlah kandidat dibatasi sekitar 1.200 (grid dikasarkan otomatis).
3. Pencarian berlapis menurut jumlah relay (dynamic programming, beam 150). Jumlah relay minimum dijamin selama kandidat per lapis tidak melebihi beam. Di antara solusi dengan jumlah relay sama dipilih biaya terendah: slack tautan ke node induk dan ke jalur, jarak ke jalur, dan kemiringan. Induk relay bisa base atau relay sebelumnya (jaringan bercabang).
4. Tiap relay digeser halus di sekitar posisi grid (polish) selama semua syarat tetap terpenuhi.
5. Geser manual di peta dinilai ulang dengan model dan angka yang sama persis.

**Parameter di panel Setup:**

| Parameter | Arti | Catatan |
|---|---|---|
| Frekuensi (MHz) | FSPL dan radius Fresnel | Bawaan 922 MHz (pita legal Indonesia 920 sampai 923 MHz, AS923, Permenkominfo 1/2019). Selisih terhadap 915 MHz hanya sekitar 0,4 persen pada perhitungan lintasan. Samakan dengan kanal aktual E220. |
| Antena pendaki / relay (m) | Tinggi antena | Tiang relay lebih tinggi mengurangi jumlah relay. |
| Hop maks (km) | Jarak maksimum satu tautan | Bawaan 2 km lebih longgar dari target C-251 (1 km LOS, 300 m NLOS). |
| Redaman medan maks (dB) | Batas kepercayaan redaman difraksi | Bawaan 6 dB. Menaikkannya menghemat relay tetapi mempercayai model di medan yang makin terhalang. |
| Cadangan galat DEM (m) | Medan dianggap segini lebih tinggi | Bawaan 1 m. Tombol utama antara hemat relay dan tahan galat DEM. |
| Daya TX, gain antena, sensitivitas | Anggaran daya | Bawaan dari C-251. Gain adalah gain **bersih** (sudah dikurangi rugi kabel dan konektor). |
| Margin fading (dB) | Margin di atas sensitivitas yang disyaratkan | Bawaan 10 dB. Saran kalibrasi: 1,28 kali sigma residu. |
| Skala vegetasi (0 sampai 1) | Pengali redaman vegetasi | 0 mengabaikan vegetasi. Turunkan bila DEM sudah memuat tinggi pohon (lihat peringatan DSM). |
| Offset kalibrasi (dB) | Redaman tambahan hasil kalibrasi | Diisi tombol "Terapkan saran" atau manual. |
| Relay maks, radius cari, langkah cari | Batas pencarian | Langkah lebih halus dari sekitar 30 m tidak berguna karena DEM efektif sekitar 30 m. |

**Data vegetasi (opsional tetapi disarankan di area berhutan).** Unggah GeoTIFF **tinggi kanopi dalam meter** di panel Setup > Konfigurasi Lanjutan, bagian 3 (`POST /api/v1/sites/active/canopy`). CRS dan resolusi bebas: berkas direproyeksi ke EPSG:4326 dan resolusi yang lebih halus dari sekitar 10 m dirata-ratakan (membatasi memori). Piksel nodata dianggap 0, area di luar raster dianggap tidak diketahui (dihitung tanpa vegetasi dan dilaporkan sebagai persen jalur yang tercakup). Berkas yang tampak seperti DEM atau kelas tutupan lahan (nilai di luar 0 sampai 150 m) ditolak. Contoh sumber: peta tinggi kanopi global ETH (10 m) atau Meta/WRI (1 m); cek cakupan dan lisensi sebelum dipakai. Data kanopi ikut lokasi: DEM baru berarti unggah ulang.

**Peringatan DSM.** Beberapa DEM adalah model permukaan (DSM) yang sudah memuat tinggi pohon (misalnya Copernicus GLO-30). Bila DEM Anda DSM, pohon terhitung dua kali (di medan dan di vegetasi). Gunakan DEM medan telanjang (DTM) bila ada, atau turunkan `skala vegetasi`. Periksa jenis DEM dari sumber aslinya.

**Kalibrasi dari RSSI lapangan** (panel Setup > Konfigurasi Lanjutan, bagian 5, `GET /api/v1/sites/active/calibration`). Perencana memprediksi RSSI tiap posisi pendaki dari base dengan model yang sama, lalu membandingkannya dengan RSSI terukur dari paket langsung (0 hop, GPS valid, 72 jam terakhir, bisa dibatasi sesi atau jarak maksimum):

- `residu = terukur - prediksi`. Saran offset = offset sekarang dikurangi median residu. Saran margin fading = 1,28 kali sigma residu (sekitar 90 persen paket di atas ambang).
- `rssi_p01_dbm` (RSSI terendah yang masih diterima) adalah batas atas sensitivitas efektif. Bandingkan dengan parameter sensitivitas.
- Tombol "Terapkan" hanya aktif bila data andal: minimal 30 paket dan rentang jarak P90/P10 minimal 2. Bila residu berubah lebih dari 8 dB per dekade jarak, offset konstan tidak cukup (eksponen redaman lapangan beda dari model) dan ada peringatan.
- **Bias sensor:** paket yang hilang tidak punya RSSI, sehingga di tepi jangkauan residu terlihat lebih baik daripada kenyataan. Kalibrasi pada jarak di mana PDR masih tinggi (isi "batas jarak").
- **Jangan kalibrasi dengan data sintetis.** Seeder menghasilkan RSSI karangan; hasilnya tidak berarti.
- Setelah menerapkan, jalankan kalibrasi lagi: median residu harus mendekati 0.

**Hasil verifikasi (DEM `klangon_dem.tif`, 7 jalur uji sintetis, hop 2 km, radius 0,45 km):**

- Semua jalur terjangkau penuh dengan 2 sampai 5 relay. Perencana greedy lama gagal menjangkau penuh 6 dari 7 jalur yang sama (dinilai dengan kriteria baru).
- Hasil divalidasi dengan penghitung skalar terpisah pada DEM asli, DEM yang dihaluskan ke setara 30 m, dan DEM bergalat acak 3 m: cakupan 100 persen pada dua yang pertama dan paling rendah 99,2 persen pada yang ketiga.
- Jumlah relay sama dengan pencarian tanpa pemangkasan beam, jadi minimal pada model dan grid kandidat yang sama.
- Tanpa raster kanopi dan dengan anggaran daya bawaan, hasil identik dengan versi sebelum link budget (posisi relay sama pada 7 dari 7 jalur): anggaran daya bawaan sangat longgar (margin sekitar 80 dB pada 0,5 km), jadi batas yang menentukan adalah redaman medan dan hop maks. Anggaran daya baru menentukan setelah offset kalibrasi dan vegetasi masuk.
- Perhitungan link divektorkan dicocokkan dengan implementasi skalar terpisah (medan, vegetasi, RSSI): selisih di bawah 1e-13 dB. Titik acuan Weissberger pada 915 MHz: 6,1 dB (14 m), 12,9 dB (50 m), 19,4 dB (100 m), 37,1 dB (300 m).
- Kalibrasi diuji pada data simulasi dengan kebenaran diketahui (offset 9,0 dB, sigma 5,0 dB): hasil 8,9 dB dan 5,0 dB; setelah diterapkan median residu 0. Uji end-to-end lewat endpoint ke PostgreSQL + PostGIS (paket via relay dan GPS tidak valid diabaikan).
- Waktu hitung sekitar 2 sampai 3 detik untuk jalur 2,5 km dan 4 sampai 6 detik untuk 5 sampai 8 km (dengan kanopi sekitar 30 persen lebih lama).
- **Belum diuji:** raster kanopi nyata (uji memakai kanopi sintetis dari DEM), data RSSI nyata, dan tampilan di browser.

**Batasan yang harus dicatat:**

- Angka mutlak RSSI prediksi **tidak dapat dipercaya sebelum dikalibrasi**. Bawaan C-251 (21 dBm, 5 dBi, -137 dBm) kemungkinan optimistis dibanding lapangan; sensitivitas efektif ditentukan dari data (`rssi_p01_dbm`), bukan hanya dari spesifikasi.
- Rintangan medan dimodelkan sebagai satu tepi pisau pada titik terburuk, tanpa beberapa tepi dan tanpa pantulan tanah.
- Vegetasi hanya ada bila raster kanopi diunggah dan akurat. Weissberger adalah model empiris; skala vegetasi dan offset kalibrasi adalah tombol penyesuaian.
- Kualitas hasil dibatasi resolusi efektif DEM (sekitar 30 m pada berkas contoh).
- Jumlah relay sangat bergantung pada cadangan galat DEM, redaman medan maks, margin fading, dan tinggi relay. Catat nilai yang dipakai di laporan.
- Medan sangat curam (kerucut puncak Merapi di atas sekitar 2.800 m) bisa membuat perencana berhenti dengan alasan tidak ada kandidat. Pesan di panel menyebut sampai berapa kilometer jalur tercover.
- Posisi relay hasil perencana adalah titik awal untuk dicoba di lapangan, lalu digeser manual sesuai kondisi sebenarnya.

## Menghubungkan Base Station

```bash
pip install pyserial asyncpg
python reference-for-hardware-team/serial_to_postgres_bridge.py --port COM5
```

Opsi:

| Opsi | Keterangan |
|---|---|
| `--port` | Port serial base station. Dipilih otomatis bila hanya ada satu port. |
| `--baud` | Baud rate, bawaan 115200. |
| `--database-url` | URL koneksi PostgreSQL. Bawaan `postgresql://silacak:silacak@localhost:5432/silacak`, dapat diganti lewat variabel lingkungan `DATABASE_URL`. |
| `--also-csv` | Menyimpan juga salinan CSV sebagai cadangan lapangan. |
| `--no-ack` | Menganggap konfigurasi sudah `acked` begitu baris `CFG` ditulis ke serial. Lihat bagian Push Konfigurasi. |

Hal yang perlu diketahui:

- Format yang diterima adalah baris `CSV_DATA` dengan 18 field setelah penanda. Bridge menerima baris dengan field lebih banyak (field tambahan diabaikan dan ada satu peringatan), tetapi menolak baris dengan field kurang. Urutan field ada di `FIELDNAMES` pada berkas bridge.
- `node_id` pada firmware dipetakan ke `hiker_code` berformat `H01`, `H02`, dan seterusnya. Node yang di halaman Setup didaftarkan sebagai relay atau base tidak diperlakukan sebagai pendaki.
- Paket tanpa GPS fix tetap disimpan dengan `location` kosong (NULL). Validitas GPS dihitung sebagai: ada koordinat, jumlah satelit minimal 4, dan HDOP paling besar 5.
- `recorded_at` diisi dari waktu GPS (`gps_utc`) bila tersedia dan masuk akal (tahun 2024 ke atas). Bila tidak, bridge memakai waktu saat paket diterima dan paket itu tidak dihitung dalam statistik latensi.
- Kolom `battery_pct` akan selalu kosong sampai firmware mengirim data baterai.
- Sinkronkan jam laptop (NTP) sebelum mengukur latensi.
- Bridge harus tetap berjalan agar data masuk dan agar konfigurasi dari dashboard terkirim.

## Mengakses Basis Data

Kredensial bawaan: database `silacak`, pengguna `silacak`, kata sandi `silacak`. Ganti sebelum dipakai di luar satu laptop tertutup.

Dari dalam container (tanpa memasang apa pun di host):

```bash
docker compose exec db psql -U silacak -d silacak
```

Dari host, dengan `psql` atau aplikasi GUI seperti DBeaver:

```bash
psql postgresql://silacak:silacak@localhost:5432/silacak
```

Untuk aplikasi GUI isi host `localhost`, port `5432`, database `silacak`, pengguna dan kata sandi `silacak`.

Dari komputer lain (misalnya bridge berjalan di PC yang mencolok ke base station, sementara Docker di laptop lain): ganti `localhost` dengan alamat IP laptop yang menjalankan Docker, mis. `--database-url postgresql://silacak:silacak@192.168.1.10:5432/silacak`. Port 5432 harus terjangkau dan tidak diblokir firewall. Hal ini membuka basis data ke jaringan, jadi baca bagian Keamanan lebih dulu.

Tabel utama: `hikers`, `hiking_sessions`, `positions` (hypertable bila TimescaleDB tersedia), `alerts`, `sites`, `devices`, `device_commands`.

Pertanyaan yang berguna saat pengujian pertama:

```sql
-- 20 paket terakhir beserta status fix
SELECT sequence, recorded_at, received_at, rssi_dbm, hop_count, route_path,
       satellites, hdop, gps_valid, gps_flags, time_from_gps,
       location IS NOT NULL AS ada_fix
FROM positions ORDER BY recorded_at DESC LIMIT 20;

-- ragam isi gps_flags dari firmware dan hubungannya dengan gps_valid
SELECT gps_flags, gps_valid, count(*) FROM positions GROUP BY 1, 2 ORDER BY 3 DESC;

-- sesi terbaru
SELECT id, status, checked_in_at, checked_out_at FROM hiking_sessions ORDER BY id DESC LIMIT 10;

-- alarm yang masih aktif
SELECT * FROM alerts WHERE status = 'ACTIVE';

-- status konfigurasi perangkat (selaras bila config_version sama dengan pushed_version)
SELECT node_id, name, role, config_version, pushed_version FROM devices;
```

Cara membersihkan data uji: `docker compose down -v`. Perintah ini menghapus seluruh isi basis data (posisi, sesi, alarm, perangkat, dan catatan lokasi). Berkas DEM dan ubin di folder `data/` tidak terhapus, tetapi karena catatan lokasinya hilang, DEM harus diunggah ulang di Setup (kosongkan dulu isi `data/sites/`).

## Push Konfigurasi ke Perangkat

Yang dimaksud di sini adalah konfigurasi radio (interval lapor, daya, air data rate) yang didorong dari dashboard. Kode firmware ESP32 tidak ada di repositori ini dan tidak dikirim lewat dashboard. Saat ini fitur ini dimatikan di UI (flag `FIRMWARE_SUPPORTS_CFG`); alur di bawah berlaku setelah firmware siap.

Alur:

1. Di Setup, tab "Perangkat", ubah konfigurasi lalu simpan. Versi konfigurasi naik dan perangkat ditandai belum sinkron.
2. Klik "Push" pada perangkat (atau tombol push untuk semua perangkat yang belum sinkron). Dashboard menaruh perintah berstatus `pending` di tabel `device_commands`.
3. Bridge memeriksa antrean setiap 2 detik dan menulis satu baris ke port serial base station:
   `CFG,<node_id>,<nama>,<peran>,<interval_lapor_detik>,<daya_dBm>,<air_data_rate_kbps>,<versi>`
4. Bila firmware membalas `CFG_ACK,<node_id>,<versi>`, status menjadi `acked` dan perangkat dianggap sinkron. Tanpa balasan, status berhenti di `sent`. Dengan opsi `--no-ack`, status langsung `acked` begitu baris ditulis.

Peringatan penting:

- Format `CFG` adalah usulan. Firmware belum tentu mengenalinya, dan belum tentu base meneruskannya ke node tujuan. Status `acked` dengan `--no-ack` tidak membuktikan perangkat menerima konfigurasi. Jangan memakai fitur ini sebagai satu-satunya cara mengubah parameter di lapangan sebelum dukungan firmware dipastikan.
- Validasi di backend: air data rate salah satu dari 2,4 / 4,8 / 9,6 / 19,2 / 38,4 / 62,5 kbps (setelan modul E220), interval lapor 5 sampai 3600 detik, daya 2 sampai 20 dBm. Rentang daya itu belum diselaraskan dengan level daya diskrit modul E220.

Untuk tim hardware, hal yang perlu dipastikan:

- Apakah base mengenali baris `CFG`, atau sesuaikan fungsi `build_cfg_line()` di bridge dengan format perintah yang sudah ada di firmware.
- Apakah base meneruskan konfigurasi ke node tujuan, dan apakah node membalas `CFG_ACK`.
- Cara membangun dan mengunggah firmware ke ESP32 mengikuti petunjuk repositori hardware (`Hadware_Programing-main`). Bagian itu tidak dicakup dokumen ini.

## Diagnostik Tautan: Definisi dan Batasan

| Besaran | Definisi | Batasan |
|---|---|---|
| PDR sesi | PDR = (N - 1) / ((N - 1) + hilang), dengan N jumlah paket diterima. Paket pertama menjadi jangkar (tidak dihitung sebagai diterima maupun hilang). "Hilang" adalah jumlah `missing_since_previous` mulai paket kedua. | Nilai hilang dihitung oleh firmware base, bukan oleh dashboard. Kehilangan beruntun di akhir sesi tidak terdeteksi, sehingga taksiran cenderung terlalu tinggi. Perilaku penghitung saat node reboot belum diverifikasi. |
| Latensi | Waktu paket tersimpan di basis data dikurangi waktu GPS pada paket. Dilaporkan sebagai P50 dan P95 per sesi, dalam detik. | Hanya paket dengan waktu dari GPS. Selisih jam laptop terhadap UTC masuk langsung ke hasil. Nilai negatif berarti jam tidak sinkron. Besaran ini memuat juga waktu tunggu sebelum pengiriman dan pemrosesan di sisi base. |
| Node basi | Tidak ada paket baru lebih lama dari ambang adaptif per sesi: 4 kali median jeda antar paket terbaru, dibatasi 15 sampai 600 detik (`backend/app/services/liveness.py`). | Interval kirim tidak diasumsikan karena firmware `pendaki_optimized` mengirim terus-menerus (jeda sekitar 0,3 detik) dan `pendaki_real` tiap 5 detik ±20 persen. Angka 30 detik di C-251 tidak ada di kode firmware. Bila paket belum cukup untuk diukur dipakai interval dari halaman Setup (cadangan), lalu 120 detik. |
| RSSI vs jarak | Hanya paket langsung (0 hop). Regresi RSSI terhadap log10 jarak memerlukan sedikitnya 5 titik dengan rasio jarak terjauh terhadap terdekat minimal 1,5. Titik dengan jarak di bawah 10 m dikeluarkan. | RSSI adalah besaran per tautan. Untuk paket via relay, jarak pendaki ke base bukan jarak tautan yang diukur, sehingga paket itu tidak dipakai. Syarat jumlah titik hanyalah syarat minimum agar regresi terdefinisi, bukan jaminan keandalan statistik. |

Akurasi GPS tidak dihitung di dashboard. Dashboard hanya menampilkan jumlah satelit dan HDOP. Hitung galat posisi secara offline terhadap titik referensi.

## Konfigurasi

Berkas `backend/.env` (salin dari `backend/.env.example`, berkas `.env` tidak ikut Git). Setelah mengubahnya, buat ulang container backend: `docker compose up -d --force-recreate backend`.

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `DATABASE_URL` | `postgresql://silacak:silacak@db:5432/silacak` | Koneksi basis data dari dalam Docker. |
| `STAGNANT_WINDOW_MINUTES` | 180 | **Tidak dipakai lagi** (deprecated). Sejak logika koridor, jendela yang dipakai adalah `STAGNANT_WINDOW_INSIDE_MINUTES` atau `STAGNANT_WINDOW_OUTSIDE_MINUTES`. Dipertahankan di `config.py` hanya agar `.env` lama tidak ditolak; tidak muncul di halaman pengaturan. |
| `STAGNANT_RADIUS_M` | 50 | Radius dianggap tidak berpindah (menentukan APAKAH pendaki diam). |
| `STAGNANT_PERIMETER_M` | 50 | Lebar koridor dari garis jalur. Di dalam koridor memakai jendela "dalam", di luar memakai jendela "luar". Belum dikalibrasi. |
| `STAGNANT_WINDOW_INSIDE_MINUTES` | 480 | Jendela diam saat posisi terakhir masih di dalam koridor (dianggap istirahat atau tidur). Belum dikalibrasi. |
| `STAGNANT_WINDOW_OUTSIDE_MINUTES` | 240 | Jendela diam saat posisi terakhir di luar koridor (dianggap lebih mungkin kecelakaan). Belum dikalibrasi. |
| `STAGNANT_CHECK_INTERVAL_MINUTES` | 2 | Seberapa sering pemeriksaan dijalankan. |
| `OFFTRAIL_DEBOUNCE_PACKETS` | 3 | Jumlah paket berfix terbaru yang semuanya harus di luar koridor sebelum alarm "di luar jalur" menyala. Belum dikalibrasi. |
| `DATA_RETENTION_DAYS` | 0 | Masa simpan data sesi pendakian yang SUDAH SELESAI, dalam hari. **0 = simpan selamanya (bawaan)**. Bila diisi, posisi, alarm, dan catatan sesi `completed` yang lebih lama dihapus permanen tiap pukul 03:30. Sesi aktif/darurat dan daftar pendaki tidak pernah disentuh. Bisa diubah dari halaman pengaturan. Pratinjau: `GET /api/v1/retention/preview?days=N`. |
| `CORS_ORIGINS` | `localhost:5173` dan `localhost:8080` | Asal yang diizinkan. |

Nilai deteksi stagnan adalah nilai awal dan belum dikalibrasi dengan data lapangan. Cara kerja koridor: setiap pemeriksaan, posisi terakhir tiap sesi aktif dihitung jaraknya ke garis jalur lokasi aktif. Bila jarak itu paling besar `STAGNANT_PERIMETER_M`, sesi dianggap di dalam koridor dan memakai `STAGNANT_WINDOW_INSIDE_MINUTES`; bila lebih jauh, memakai `STAGNANT_WINDOW_OUTSIDE_MINUTES`. `STAGNANT_RADIUS_M` tetap menentukan apakah pendaki dianggap diam. Bila lokasi aktif belum punya jalur (kurang dari dua titik), deteksi stagnan tidak dijalankan sama sekali (tidak ada acuan koridor); hanya SOS manual dari hardware yang tetap bekerja. Untuk menguji alarm dengan cepat, turunkan jendela "dalam" dan "luar" menjadi 1 sampai 2 menit. Keenam ambang deteksi (`STAGNANT_RADIUS_M`, `STAGNANT_PERIMETER_M`, `STAGNANT_WINDOW_INSIDE_MINUTES`, `STAGNANT_WINDOW_OUTSIDE_MINUTES`, `STAGNANT_CHECK_INTERVAL_MINUTES`, `OFFTRAIL_DEBOUNCE_PACKETS`) ada di daftar putih pengaturan operator, jadi bisa diubah dari wizard `/awal` atau halaman `/pengaturan` (juga lewat tombol Pengaturan di dashboard) tanpa mengubah kode atau env. Nilai itu berlaku per pemasangan (per laptop/instalasi, disimpan di `DATA_DIR/app_settings.json`), bukan per lokasi pendakian: mengganti lokasi aktif di Setup tidak mengubahnya.

## Data Sintetis (Pengembangan)

Untuk mengembangkan dashboard tanpa hardware:

```bash
docker compose exec backend python scripts/seed_synthetic_data.py
```

Skrip mensimulasikan tiga pendaki: H01 dan H02 bergerak di sepanjang jalur, sedangkan H03 sengaja diam untuk menguji alarm stagnan. Jalur mengikuti lokasi aktif di halaman Setup bila ada. Bila tidak ada, dipakai `TRAIL_WAYPOINTS` bawaan yang koordinatnya hanya perkiraan, bukan hasil digitasi GPX asli.

Keterbatasan seeder saat ini: skrip tidak mengisi `missing_since_previous`, `time_from_gps`, dan `gps_valid`. Akibatnya dengan data sintetis kartu PDR selalu 100 persen, latensi kosong (tampil sebagai strip), dan status GPS tidak pernah invalid. Panel itu baru bermakna dengan data dari bridge, atau setelah seeder diperbarui (lihat G14).

Peringatan: data sintetis masuk ke basis data yang sama dengan data nyata dan memakai kode perangkat yang sama (H01 dan seterusnya). Sebelum pengujian dengan hardware, kosongkan basis data dengan `docker compose down -v`.

Skrip `backend/scripts/plan_relays.py` menjalankan perencana relay dari terminal dan mencetak induk, hop, redaman, lereng, dan jarak ke jalur tiap relay. Preset `ft_ugm` memakai elevasi sintetis hanya untuk membuktikan kode berjalan, bukan untuk validasi propagasi. Preset `bukit_klangon` membaca DEM dari variabel lingkungan `DEM_PATH` (bawaan `/app/data/sites/1/dem.tif`, yaitu DEM hasil unggah di Setup):

```bash
docker compose exec backend python scripts/plan_relays.py ft_ugm
docker compose exec backend python scripts/plan_relays.py bukit_klangon
# bila lokasi aktif bukan nomor 1:
docker compose exec -e DEM_PATH=/app/data/sites/2/dem.tif backend python scripts/plan_relays.py bukit_klangon
```

## Struktur Folder

```
.gitignore                   berkas yang tidak ikut Git (.env, isi data/, cache)
docker-compose.yml
backend/
  Dockerfile, requirements.txt
  .env, .env.example         konfigurasi (lihat bagian Konfigurasi); .env tidak ikut Git
  app/
    main.py                  titik masuk, startup basis data, listener, penjadwal, /health
    core/                    config, pool basis data, penjadwal, schema.py (migrasi otomatis)
    api/v1/                  rute: hikers, positions, alerts, gpx, terrain, sites,
                             sessions, devices, diagnostics, stream
    services/                stagnant_detector, notifier, gpx_exporter,
                             dem_ingest (DEM + kanopi), terrain_planner (perencana, model tautan),
                             link_calibration (kalibrasi RSSI lapangan)
    repositories/            lapisan SQL (asyncpg)
    schemas/                 model Pydantic
  scripts/                   seed_synthetic_data.py, plan_relays.py, load_sample_site.py
frontend/
  Dockerfile, index.html, package.json, vite.config.js (proxy /api ke :8000 saat dev)
  src/
    main.js, App.vue         pemasangan aplikasi, tata letak, polling diagnostik
    components/              MapView, MonitoringPanel, WorkspacePanel, SetupPanel,
                             SessionsPanel, SosOverlay, RssiScatter, GpxExportButton
                             (_AlertPanel.vue dan _HikerList.vue adalah sisa versi lama,
                             tidak diimpor di mana pun, aman dihapus)
    stores/                  Pinia: hikers, alerts, sessions, devices, site, diagnostics
    composables/             useLiveStream (EventSource)
    services/api.js
  nginx.conf                 meneruskan /api ke backend dengan proxy_buffering off (wajib untuk SSE)
infra/postgres/
  Dockerfile                 build PostGIS ditambah TimescaleDB lewat apt (profil server; PostGIS tidak lagi dipakai aplikasi)
  init.sql                   ekstensi opsional (TimescaleDB); skema ada di backend/app/core/schema.py
reference-for-hardware-team/
  serial_to_postgres_bridge.py, README.md
samples/
  klangon_dem.tif            DEM contoh Bukit Klangon untuk diunggah di Setup (ikut Git)
  klangon_dem_clip.tif       DEM Klangon versi dipotong kecil (uji cepat)
  klangon_canopy.tif         raster tinggi kanopi Klangon (opsional, untuk model vegetasi)
  merapi_dem.tif             DEM contoh Merapi
  ftugm_dem_test.tif         DEM sintetis mini FT UGM (hanya untuk tes kode, bukan demo peta)
data/
  .gitkeep                   penjaga folder; isi lain dibuat otomatis dan tidak ikut Git
                             (data/sites/<id>/ berisi DEM dan ubin hasil unggahan)
```

### Yang tidak ikut Git

| Jalur | Alasan |
|---|---|
| `backend/.env` | Konfigurasi lokal. Salin dari `backend/.env.example`. |
| `data/*` (kecuali `data/.gitkeep`) | Hasil olahan DEM yang dibuat ulang otomatis, ratusan megabita, dan hanya terpakai bila ada baris lokasi di basis data. |
| `node_modules/`, `frontend/dist/` | Hasil `npm install` dan build. |
| `__pycache__/`, `*.pyc`, `.venv/` | Cache dan lingkungan Python. |

### API ringkas

Seluruh rute berada di bawah `/api/v1`. Dokumentasi lengkap tersedia di `/docs`.

| Kelompok | Fungsi |
|---|---|
| `hikers`, `positions` | Daftar pendaki, posisi terakhir, jejak. |
| `sessions` | Check-in, check-out, daftar sesi, jejak per sesi. |
| `alerts` | Daftar alarm dan acknowledge. |
| `diagnostics` | Ringkasan per sesi aktif dan packet log per perangkat. |
| `devices` | Perangkat, konfigurasi, push, dan antrean perintah. |
| `sites` | Lokasi aktif, unggah DEM, input, posisi relay, rencana, ekspor GPX rencana. |
| `gpx` | Ekspor jejak per sesi atau per perangkat. |
| `stream` | Aliran SSE untuk pembaruan real-time. |
| `terrain` | `GET /terrain/profile` belum diimplementasikan dan mengembalikan 501. Perencanaan relay ada di `sites`. |

## Keamanan

Sistem ini dirancang untuk satu laptop tertutup di basecamp. Sebelum dipakai di luar kondisi itu:

- Tidak ada autentikasi dan tidak ada enkripsi. Siapa pun yang dapat membuka port 8080 atau 8000 dapat membaca dan mengubah data.
- Kredensial basis data adalah bawaan (`silacak` untuk pengguna dan kata sandi) dan port 5432 terbuka ke host. Ganti kredensial dan tutup port bila ada akses dari luar.
- Sesi menyimpan nama, nomor telepon, kontak darurat, dan riwayat posisi, yang termasuk data pribadi. Belum ada kebijakan retensi dan persetujuan pendaki.
- Pembatasan koneksi per origin pada HTTP/1.1 (umumnya enam) membatasi jumlah tab dashboard yang terbuka bersamaan karena SSE.
- Penyiaran SSE berada di memori satu proses, cukup untuk satu basecamp.

## Batasan yang Diketahui

Butir berikut tidak dibela sebagai perubahan karena belum memenuhi C-251.

| ID | Kesenjangan | Dampak | Penutupan |
|---|---|---|---|
| G01 | Tidak ada penanda SOS manual pada `CSV_DATA` | Spesifikasi 6 tidak dapat diuji | Firmware menambah field SOS di belakang baris. Bridge sudah menoleransi field tambahan. |
| G02 | Tidak ada data baterai | `battery_pct` selalu kosong, spesifikasi 7 tidak terpantau | Firmware menambah pengukuran tegangan baterai |
| G03 | Tidak ada SNR | Analisis margin tautan tidak lengkap | Firmware menambah field SNR dari modul radio (periksa dulu apakah E220 mengeksposnya) |
| G04 | Hanya satu nilai RSSI per paket | Kalibrasi tautan via relay belum mungkin | Firmware relay meneruskan RSSI per hop |
| G05 | Rekomendasi penyebab error otomatis (C-251 Tabel 6.1) belum ada | Dashboard menampilkan indikator mentah | Tidak dibuat sebelum G03 dan G04 terpenuhi, karena atribusi penyebab tanpa data per hop bersifat spekulasi |
| G06 | Batasan unik per paket belum diterapkan | Paket ganda (mis. pada mesh) dapat tersimpan dan membiaskan PDR | Tambah indeks unik. Pada hypertable, kolom partisi waktu wajib ikut dalam indeks unik. |
| G07 | Vegetasi hanya dihitung bila raster tinggi kanopi diunggah | Tanpa raster, hasil optimistis di hutan; DEM berjenis DSM menghitung pohon dua kali | Unggah kanopi, periksa jenis DEM, validasi lapangan |
| G08 | Relay belum dibangun | Uji multi-hop dan latensi 2 hop belum dilakukan | Bangun relay dan ulangi uji |
| G09 | Frekuensi bawaan perencana 915 MHz (C-251: 923 MHz), validasi daya 2 sampai 20 dBm | Selisih radius Fresnel sekitar 0,44 persen, tidak mengubah kesimpulan | Samakan dengan kanal aktual E220 dan level daya diskrit modul |
| G10 | Peta jalan OSM offline lokal belum ada | Tanpa internet hanya peta topo | Unduh ubin OSM area uji ke penyimpanan lokal |
| G11 | Waktu render di peramban tidak dicatat | Spesifikasi 5 hanya terukur sampai penyimpanan | Catat waktu tiba SSE di klien atau ukur manual |
| G12 | Parameter alarm stagnan belum terkalibrasi, termasuk perimeter koridor 50 m dan jendela dalam 480 menit serta luar 240 menit | Alarm palsu belum terukur; pemilihan jendela dalam atau luar bergantung pada akurasi GPS di bawah kanopi | Kalibrasi dari data lapangan; uji sesi di dalam dan di luar koridor terhadap Postgres sungguhan (lihat catatan T2 di `docs/STATUS.md`) |
| G13 | Salinan baca-saja untuk pihak eksternal belum ada | Pihak luar belum dapat melihat daftar pendaki | Di luar lingkup versi ini |
| G15 | Angka anggaran daya (daya TX, gain, sensitivitas) masih bawaan C-251 | RSSI prediksi mutlak belum terbukti | Ukur di lapangan, lalu kalibrasi (Setup > Konfigurasi Lanjutan, bagian 5) dan verifikasi sensitivitas ke datasheet |
| G14 | Seeder tidak mengisi `missing_since_previous`, `time_from_gps`, `gps_valid` | Panel PDR, latensi, dan status GPS tidak teruji dengan data sintetis | Perbarui seeder: simulasikan paket hilang, waktu GPS, dan fix buruk sesekali |

Tambahan: hasil pengujian di satu lokasi tidak dapat diekstrapolasi ke lokasi lain tanpa kalibrasi ulang.

## Langkah Selanjutnya

Urutan disarankan dari yang paling mendesak.

### 1. Verifikasi pertama (sekarang, tanpa hardware tambahan)

- [ ] `docker compose up --build` berhasil, `/health` menjawab, dan skema termigrasi (cek tabel `positions` memiliki kolom `gps_valid`, `gps_flags`, `time_from_gps`).
- [ ] Unggah `samples/klangon_dem.tif` di Setup (atau jalankan `scripts/load_sample_site.py`) dan pastikan peta topo offline muncul.
- [ ] Jalankan data sintetis, pastikan peta, sesi, dan alarm stagnan berfungsi, lalu `docker compose down -v` untuk membersihkan. Ingat bahwa PDR dan latensi tidak teruji oleh seeder saat ini (G14).
- [ ] Sambungkan base station dan cek dengan SQL (bagian Mengakses Basis Data) bahwa paket masuk. Temuan dari kode firmware: saat tidak ada fix, firmware mencetak koordinat `0.0000000,0.0000000` (bukan kosong) dan bit `LocationValid` (`gps_flags & 1`) tidak di-set. Parser sekarang memakai bit itu sehingga paket tanpa fix disimpan dengan lokasi NULL; perlu dikonfirmasi dengan data lapangan.
- [ ] Sinkronkan jam laptop (NTP).
- [ ] Verifikasi apakah `missing_since_previous` terisi dengan benar. Bila selalu 0, PDR akan terbaca 100 persen dan tidak berarti.

### 2. Pengujian yang sudah bisa dilakukan dengan base dan satu portable node

- [ ] Uji tautan langsung: PDR (target sesi minimal 100 paket, ideal sekitar 140 atau lebih), jangkauan, dan kalibrasi n serta sigma pada jalur terbuka.
- [ ] Uji akurasi GPS statis: kumpulkan sampel pada titik referensi, hitung galat offline.
- [ ] Uji latensi dan waktu pembaruan, dengan jam yang sinkron.
- [ ] Uji alarm stagnan dengan jendela diperpendek, lalu kembalikan ke nilai bawaan.
- [ ] Catat konfigurasi radio aktual (kanal atau frekuensi, SF, BW, daya) dan versi firmware yang dipakai.

### 3. Membutuhkan perubahan hardware atau firmware

- [ ] Tambah field SOS, baterai, dan SNR pada `CSV_DATA` (G01 sampai G03). Setelah itu perbarui `FIELDNAMES` dan perintah `INSERT` di bridge, serta buat alarm `MANUAL_SOS` dan `LOW_BATTERY` dari bridge. Tipe alarm sudah tersedia di basis data dan tampilan overlay sudah ada.
- [ ] Pastikan firmware mengenali baris `CFG` dan membalas `CFG_ACK`, atau sesuaikan `build_cfg_line()`.
- [ ] Setelah relay dibangun: RSSI per hop (G04), heartbeat relay agar statusnya terlihat, lalu ulangi uji multi-hop dan latensi 2 hop.

### 4. Perangkat lunak

- [ ] Terapkan indeks unik paket (G06).
- [ ] Samakan frekuensi perencana dengan kanal aktual dan selaraskan validasi daya (G09).
- [ ] Unggah raster tinggi kanopi lokasi uji dan pastikan jenis DEM (DTM atau DSM) (G07).
- [ ] Setelah ada RSSI lapangan: jalankan kalibrasi (Setup > Konfigurasi Lanjutan, bagian 5), terapkan saran offset dan margin fading, lalu hitung ulang rencana relay (G15). Catat nilai sebelum dan sesudah di laporan.
- [ ] Unduh ubin OSM offline area uji (G10) dan catat waktu render di klien (G11).
- [ ] Sebelum dipakai di luar satu laptop tertutup: autentikasi, enkripsi, ganti kredensial, dan kebijakan retensi data pribadi.
- [ ] Tambah pengujian otomatis (minimal untuk parser bridge, perhitungan PDR, dan deteksi stagnan).

### 5. Dokumentasi

- [ ] Perbarui draf C-601 dengan hasil uji (semua penanda `[ISI]`), lalu cocokkan register perubahan dengan kondisi akhir kode.
- [ ] Siapkan bukti kontribusi dari riwayat Git (commit dan blame) untuk bab kontribusi individu.

## Pemecahan Masalah

| Gejala | Kemungkinan penyebab dan langkah |
|---|---|
| `docker compose up` gagal karena `backend/.env` tidak ditemukan | Berkas itu tidak ikut Git. Salin dari contoh: `cp backend/.env.example backend/.env`. |
| Peta topo tidak muncul setelah clone baru | Basis data masih kosong. Lokasi dibaca dari tabel `sites`, jadi berkas di `data/` saja tidak cukup. Unggah `samples/klangon_dem.tif` di Setup atau jalankan `docker compose exec backend python scripts/load_sample_site.py`. |
| `load_sample_site.py` melapor "Berkas tidak ditemukan" | Volume `samples` belum terpasang di container. Jalankan `docker compose up -d` agar container dibuat ulang, dan pastikan folder `samples/` ada di root repositori. |
| Posisi tidak muncul padahal bridge berjalan | Baca keluaran bridge: baris dengan kurang dari 18 field ditolak. Cek apakah Node ID itu didaftarkan sebagai `relay` atau `base` di Setup (paketnya diabaikan). Cek dengan SQL bagian Mengakses Basis Data. |
| Marker diam di lokasi lama dan ada lencana "gps invalid" | Paket terbaru tanpa fix atau Nsat di bawah 4 atau HDOP di atas 5. Marker tetap di lokasi fix terakhir. Itu perilaku yang dirancang. |
| Dashboard tidak memperbarui sama sekali | Pastikan diakses lewat nginx (port 8080) dan `proxy_buffering off` tidak diubah. Tutup tab yang tidak perlu (batas sekitar enam koneksi SSE per origin). Lihat `docker compose logs backend`. |
| "pdr sesi" selalu 100 persen | `missing_since_previous` selalu 0 atau kosong (firmware belum mengisinya, atau data berasal dari seeder, lihat G14). |
| Latensi kosong atau negatif | Kosong: paket tanpa waktu GPS (tahun di bawah 2024) tidak dihitung. Negatif: jam laptop tidak sinkron. Sinkronkan NTP. |
| Jarak ke base tampil sebagai strip | Titik base belum di-set di Setup, atau paket itu tanpa fix. |
| DEM berstatus error setelah unggah | Pesan alasannya tampil di Setup. Backend yang mati saat memproses menandai error saat start berikutnya. Unggah ulang. Bila gagal karena izin, periksa kepemilikan folder `data/`. |
| Konfigurasi perangkat berhenti di `sent` | Firmware tidak membalas `CFG_ACK`. Lihat bagian Push Konfigurasi. |
| Alarm muncul tanpa suara | Peramban memblokir audio sebelum ada interaksi. Klik halaman sekali. |
| Perubahan `backend/.env` tidak berlaku | Buat ulang container: `docker compose up -d --force-recreate backend`. |

## Catatan Teknis

- Layanan `db` dibuat dari `infra/postgres/Dockerfile` (basis `postgis/postgis`, TimescaleDB ditambahkan lewat apt), bukan dari image siap pakai `timescale/timescaledb-ha`. Image itu sempat gagal mengubah izin folder data pada Docker Desktop for Windows (WSL2).
- Penjadwal memakai `misfire_grace_time=30` detik. Nilai bawaan satu detik membuat pemeriksaan alarm sering terlewat akibat timer jitter di Docker.
- Proses DEM yang terputus karena backend mati ditandai galat pada startup berikutnya, agar tidak terlihat memproses selamanya.
- Perubahan skema dilakukan lewat `schema.py` (idempotent) dan berlaku untuk basis data baru maupun lama.
- Koordinat bawaan pada peta dan data sintetis diarahkan ke Bukit Klangon (Cangkringan, Sleman) sebagai perkiraan dari sumber online, bukan hasil digitasi GPX. Bila jalur target berada di kawasan taman nasional, pastikan izin masuk dan status akses jalur terbaru sebelum uji lapangan.

## Status kekurangan yang tercatat di laporan

Dipisahkan menurut apa yang menghalangi. Yang bertanda **dikerjakan** sudah ada kodenya dan tesnya; itu tidak sama dengan "sudah
dikalibrasi" atau "sudah memenuhi hukum": angka dan keputusan akhirnya tetap butuh data lapangan atau penilaian lembaga.

| Kekurangan | Status | Keterangan |
|---|---|---|
| Penyebab penumpukan paket base -> baca serial | **Alat ukur dikerjakan**, penyebabnya belum diketahui | Firmware base SUDAH mengirim `base_received_uptime_ms` di tiap `CSV_DATA`. Backend membandingkan selisihnya dengan jam baca laptop dan melaporkan penundaan ekstra serta apakah penahannya di laptop atau sebelum pembacaan: `GET /api/v1/diagnostics/serial-timing` (juga kartu "Penumpukan paket di serial" di tab Link). Menunjuk satu penyebab pasti (antrean TX serial di firmware, buffer USB-serial, atau driver) masih butuh pengukuran di sisi firmware. |
| Waktu tiba SSE dan penggambaran di peramban | **Dikerjakan** | Tiap paket posisi dicatat: SSE tiba, lalu layar diperbarui (aproksimasi: DOM selesai + satu frame dicat). Ringkasan p50/p95 per tahap dan unduh CSV ada di tab Link. `serial_read_at` (laptop membaca baris) kini disimpan dan ikut di NOTIFY, jadi tahap baca-serial -> DB -> SSE -> layar terukur terpisah. Selisih yang melibatkan jam GPS hanya sah bila jam laptop sinkron. |
| Kalibrasi perencana relay dengan RSSI lapangan; sensitivitas | **Butuh data lapangan** | Alat kalibrasinya sudah ada: `GET /api/v1/sites/active/calibration` membandingkan RSSI terukur dengan prediksi dan menaksir `calib_offset_db`, simpangan (untuk `fade_margin_db`), dan kemiringan sisa (penanda bentuk model keliru). Model yang dipakai perencana memakai FSPL + difraksi medan + vegetasi + satu offset, TIDAK memiliki eksponen `n` atau `a`; istilah itu milik model simulasi lain. Sensitivitas pada laju data udara yang dipakai harus diukur dengan perangkat keras (kurva paket-hilang terhadap daya). |
| Kalibrasi ambang Auto-SOS dan OFF_TRAIL; evaluasi alarm palsu | **Alat evaluasi dikerjakan**, kalibrasi butuh data | `python scripts/eval_alarms.py --fixes rekaman.csv --trail jalur.gpx [--truth truth.csv] --grid "perimeter=20,50,100;debounce=1,3,5"` memutar ulang rekaman dengan rumus detektor yang sama dan menghitung alarm palsu serta tunda deteksi per kombinasi. Logika STAGNANT-nya dicocokkan dengan query SQL asli di `tests/test_db_integration.py`. Ambang yang aman tetap harus ditetapkan dari banyak rekaman (kanopi, cuaca, pola istirahat). |
| Sinkronisasi jam laptop dengan waktu GPS | **Deteksi dikerjakan**, sinkronisasi tidak | Backend menilai kesinkronan jam dari latensi negatif (`clock_check` di `/diagnostics`) dan dashboard memperingatkan di tab Link. Mengubah jam Windows butuh hak administrator dan tidak dilakukan aplikasi; jam base belum dikirim ke laptop oleh firmware. |
| Indeks unik per paket (anti-ganda) | **Dikerjakan** | `uq_positions_packet (hiker_id, sequence, recorded_at, sos)` + `ON CONFLICT DO NOTHING`; paket ganda tidak disimpan dan tidak memicu SSE dua kali. Tidak menghapus data otomatis: bila DB lama berisi paket ganda, indeks tidak dibuat dan backend memberi peringatan; bersihkan dengan `python scripts/dedupe_positions.py --apply`. Paket tanpa jam GPS atau tanpa nomor urut tidak bisa dideduplikasi. PDR per segmen (per hop) belum dihitung. |
| Kebijakan masa simpan data | **Mekanisme dikerjakan, angkanya bukan keputusan aplikasi** | `DATA_RETENTION_DAYS` (lihat tabel env), mati secara bawaan. Aplikasi tidak menentukan lama simpan yang sah menurut UU Pelindungan Data Pribadi: itu ditetapkan lembaga pengelola bersama penasihat hukumnya. |
| Autentikasi dan enkripsi | **Belum dikerjakan** | Aplikasi mendengarkan hanya `127.0.0.1` pada mode portabel. Autentikasi berarti mengubah peluncur, `EventSource` (tidak bisa mengirim header), dan frontend, dan butuh keputusan desain. Enkripsi data diam paling tepat lewat enkripsi disk (BitLocker); enkripsi tingkat aplikasi belum ada. Memasang aplikasi ini di jaringan (Docker/LAN) tanpa lapisan autentikasi di depannya tidak aman. |
| Antrean konfigurasi dari dashboard | **Tertahan firmware** | Sisi backend sudah ada dan dijaga flag `FIRMWARE_SUPPORTS_CFG` (mati). Firmware base saat ini tidak membaca data serial masuk (tidak ada `CFG`/`CFG_ACK`). Menyalakan flag sebelum firmware siap membuat perintah menggantung. |