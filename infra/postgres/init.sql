-- Skema (tabel, fungsi, trigger) dibuat & dimigrasi oleh backend saat start: backend/app/core/schema.py.
-- File ini hanya menyiapkan extension OPSIONAL untuk profil server (Docker Compose).
-- Dashboard tetap jalan di PostgreSQL polos tanpa TimescaleDB (mode portable);
-- PostGIS tidak dipakai lagi (jarak dihitung Haversine di SQL).
CREATE EXTENSION IF NOT EXISTS timescaledb;
