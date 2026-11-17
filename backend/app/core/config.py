from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://silacak:silacak@localhost:5432/silacak"

    # Parameter Auto-SOS, sengaja dibuat configurable (bukan hardcode)
    # karena radius & window perlu dikalibrasi ulang pakai data GPS
    # asli di lapangan (akurasi GPS di bawah kanopi bisa drift 10-30m).
    # DEPRECATED, TIDAK DIPAKAI detektor sejak logika koridor (lihat stagnant_window_inside/outside_minutes
    # di bawah). Dipertahankan hanya supaya berkas .env lama yang masih memuatnya tidak ditolak pydantic.
    stagnant_window_minutes: int = 180
    stagnant_radius_m: float = 50.0
    stagnant_check_interval_minutes: int = 2

    # Perimeter/koridor di sekitar jalur pendakian. Kalau posisi TERAKHIR pendaki masih di dalam
    # koridor (<= stagnant_perimeter_m dari garis trail), diam dianggap wajar (istirahat/tidur) ->
    # window panjang. Kalau di LUAR koridor (menyimpang dari jalur), diam mencurigakan (kecelakaan)
    # -> window pendek. stagnant_radius_m tetap menentukan APAKAH pendaki diam; nilai di bawah hanya
    # memilih BERAPA LAMA toleransinya.
    # ASUMSI BELUM DIKALIBRASI (belum diuji di lapangan, seperti catatan di app_settings.py):
    # 50 m koridor, 480 menit (~8 jam, satu malam tidur) di dalam, 240 menit (4 jam) di luar.
    stagnant_perimeter_m: float = 50.0
    stagnant_window_inside_minutes: int = 480
    stagnant_window_outside_minutes: int = 240

    # Peringatan dini "di luar jalur" (off_trail_watch): berapa paket berfix TERBARU yang semuanya harus
    # di luar koridor sebelum alarm menyala (menapis lonjakan GPS satu paket). Paket ~5 dtk sekali ->
    # 3 paket ~15 dtk. ASUMSI BELUM DIKALIBRASI.
    offtrail_debounce_packets: int = 3

    # Masa simpan data sesi pendakian yang SUDAH SELESAI (hari). 0 = simpan selamanya (bawaan; tidak ada yang dihapus).
    # Lihat app/services/retention.py untuk daftar yang dihapus dan yang tidak.
    data_retention_days: int = 0

    # Folder data (DEM/tile hasil Setup, log mentah serial). Sama dengan env DATA_DIR yang dibaca sites.py.
    data_dir: str = "/app/data"

    # Kalau diisi (folder hasil `npm run build`), backend sendiri yang menyajikan dashboard di "/"
    # -> tidak butuh nginx/Node (dipakai mode portable). Kosong = backend API saja (Docker/dev).
    frontend_dir: str | None = None

    # Ingest serial base station yang tertanam di backend. "off" (bawaan, kompatibel dengan
    # bridge eksternal) | "auto" (cari ESP32 sendiri) | "COM5" / "/dev/ttyUSB0".
    serial_port: str = "off"
    serial_baud: int = 115200
    serial_no_ack: bool = False   # firmware belum membalas CFG_ACK; True = anggap 'acked' begitu ditulis
    # Firmware real v2 (base_real.cpp) TIDAK membaca serial masuk, jadi baris `CFG,...` dari dashboard tidak akan pernah
    # diterima/dikonfirmasi. False = push konfigurasi ditolak dengan pesan jelas. Ubah ke True HANYA setelah firmware
    # base mendukung CFG + CFG_ACK.
    firmware_supports_cfg: bool = False
    raw_log: bool = True          # simpan setiap baris CSV_DATA mentah (append-only) di data_dir/raw/

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
