# Base image postgis/postgis dipakai (bukan timescale/timescaledb-ha) karena
# base ini masih pakai entrypoint standar docker-library/postgres yang
# terbukti stabil nge-handle permission volume di semua platform, termasuk
# Docker Desktop for Windows (WSL2) - beda dari image *-ha yang entrypoint
# kustomnya sering gagal chown folder data di WSL2 (lihat README bagian
# Troubleshooting).
FROM postgres:16-bookworm

# 1. Update OS dan install dependencies dasar
# 2. Install PostGIS 3 untuk PostgreSQL 16
# 3. Tambahkan repositori TimescaleDB dan install ekstensi TimescaleDB
RUN apt-get update && apt-get install -y --no-install-recommends \
        gnupg lsb-release ca-certificates curl \
        postgresql-16-postgis-3 \
        postgresql-16-postgis-3-scripts \
    && echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -c -s) main" \
        > /etc/apt/sources.list.d/timescaledb.list \
    && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends timescaledb-2-postgresql-16 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Buat script agar extension postgis otomatis terpasang saat database pertama kali dibuat
RUN mkdir -p /docker-entrypoint-initdb.d \
    && echo 'CREATE EXTENSION IF NOT EXISTS postgis;' > /docker-entrypoint-initdb.d/10_postgis.sql \
    && echo 'CREATE EXTENSION IF NOT EXISTS postgis_topology;' >> /docker-entrypoint-initdb.d/10_postgis.sql

# initdb pakai postgresql.conf.sample ini sebagai template - shared_preload_libraries
# WAJIB di-set sebelum extension timescaledb bisa dipakai.
RUN echo "shared_preload_libraries = 'timescaledb'" >> /usr/share/postgresql/postgresql.conf.sample