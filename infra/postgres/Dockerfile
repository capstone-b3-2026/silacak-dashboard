# Base image postgis/postgis dipakai (bukan timescale/timescaledb-ha) karena
# base ini masih pakai entrypoint standar docker-library/postgres yang
# terbukti stabil nge-handle permission volume di semua platform, termasuk
# Docker Desktop for Windows (WSL2) - beda dari image *-ha yang entrypoint
# kustomnya sering gagal chown folder data di WSL2 (lihat README bagian
# Troubleshooting).
FROM postgis/postgis:16-3.4

# Base image ini masih Debian 11 "bullseye" (belum di-update ke bookworm
# oleh maintainer postgis/postgis per Sept 2026). LTS bullseye resmi
# berakhir 31 Agustus 2026 - repo "bullseye-security" sekarang rusak:
# indexnya masih nunjuk ke file yang udah dihapus dari server (404 massal).
# Repo "bullseye" & "bullseye-updates" biasa masih normal, jadi cukup matiin
# baris security-nya aja. Kita nggak butuh patch security buat container DB
# yang cuma jalan lokal/offline, bukan yang exposed ke internet.
RUN sed -i '/bullseye-security/d' /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
        gnupg lsb-release ca-certificates curl \
    && echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -c -s) main" \
        > /etc/apt/sources.list.d/timescaledb.list \
    && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends timescaledb-2-postgresql-16 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# initdb pakai postgresql.conf.sample ini sebagai template - shared_preload_libraries
# WAJIB di-set sebelum extension timescaledb bisa dipakai.
RUN echo "shared_preload_libraries = 'timescaledb'" >> /usr/share/postgresql/postgresql.conf.sample
