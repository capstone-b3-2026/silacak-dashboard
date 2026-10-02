# Buat Tim Hardware/Ingestion

Folder ini **bukan bagian dari scope dashboard** — cuma referensi biar
cepat nyambungin base station kalian ke database `silacak`.

## Apa yang gua temuin dari review `Hadware_Programing-main`

- `base_real.cpp` dan `base_optimized.cpp` sama-sama nyetak baris
  `CSV_DATA,...` yang machine-parseable ke Serial/USB (formatnya identik
  di kedua mode, jadi bridge ini jalan buat dua-duanya).
- `tools/serial_logger.py` yang udah ada itu **parsing-nya udah bener** —
  script di sini cuma adaptasi tujuan tulisnya dari CSV ke Postgres,
  bukan nulis ulang parser dari nol.
- Field yang tersedia: `sequence`, `node_id`, `route` (jalur hop),
  `relay_hops`, `gps_utc`, `latitude`, `longitude`, `altitude_m`,
  `speed_kph`, `satellites`, `hdop`, `rssi_dbm`, `missing_since_previous`,
  `total_missing`.
- **Tidak ada** field baterai di paket data saat ini — kolom
  `battery_pct` di table `positions` akan selalu `NULL` sampai ada revisi
  hardware yang nambahin sensor itu.

## Cara pakai

```bash
pip install pyserial asyncpg
python serial_to_postgres_bridge.py --port COMy
```

Tambahkan `--also-csv` kalau tetap mau simpan file CSV sebagai backup
lapangan (nggak ganggu proses insert ke Postgres, jalan dua-duanya).

Pastikan service `db` di `docker-compose.yml` (folder utama, bukan di
sini) udah nyala dan port `5432`-nya ke-expose ke host — defaultnya
sudah begitu, tinggal `docker compose up` dari folder root project.

## Konvensi penting

- `node_id` di firmware (integer 1, 2, 3, ...) dipetakan ke `hiker_code`
  format `H01`, `H02`, ... di database. Kalau kode belum ada di table
  `hikers`, bridge ini otomatis bikin barunya — tapi idealnya tim lapangan
  daftarin dulu nama asli tiap pendaki lewat endpoint
  `POST /api/v1/hikers` biar nggak cuma nongol sebagai "H01" tanpa nama
  di dashboard.
- `recorded_at` diisi dari `gps_utc` (waktu asli dari GPS di node), bukan
  dari `tracker_uptime_ms`/`base_received_uptime_ms` yang cuma hitungan
  `millis()` sejak boot ESP32.
