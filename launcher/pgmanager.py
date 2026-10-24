"""Mengelola PostgreSQL portable (tanpa Docker, tanpa instalasi) untuk mode basecamp.

Layout yang diharapkan:  <pg_bin>/initdb(.exe), pg_ctl(.exe), createdb(.exe)
(binary PostgreSQL "zip/portable" resmi; tidak perlu PostGIS maupun TimescaleDB).

Aman dari bentrok: hanya mendengarkan 127.0.0.1 di port bebas yang dipilih sendiri, password acak
disimpan di config pengguna. Semua pemanggilan proses lewat `runner` supaya bisa diuji tanpa Postgres.
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

_WIN = os.name == "nt"
_NOWINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if _WIN else 0


class PgError(RuntimeError):
    pass


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_free_port(preferred: int | None = None, start: int = 54320, end: int = 54420) -> int:
    if preferred and port_free(preferred):
        return preferred
    for p in range(start, end):
        if port_free(p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # terakhir: minta OS
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_password() -> str:
    return secrets.token_urlsafe(24)


def _run(cmd, quiet: bool = False, **kw):
    """quiet=True untuk perintah yang meninggalkan proses anak (pg_ctl start/stop): TANPA pipa.
    Di Windows postgres.exe mewarisi pipa stdout/stderr, jadi capture_output menunggu EOF yang
    baru datang saat Postgres mati -> launcher menggantung. Keluaran start dibaca dari file log."""
    if quiet:
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, creationflags=_NOWINDOW, **kw)
    return subprocess.run(cmd, capture_output=True, text=True, creationflags=_NOWINDOW, **kw)


class PgManager:
    def __init__(self, pg_bin, data_dir, log_file, port: int, password: str,
                 user: str = "silacak", db: str = "silacak", runner=_run):
        self.pg_bin = Path(pg_bin)
        self.data_dir = Path(data_dir)
        self.log_file = Path(log_file)
        self.port, self.password, self.user, self.db = port, password, user, db
        self._run = runner

    def _exe(self, name: str) -> str:
        return str(self.pg_bin / (name + (".exe" if _WIN else "")))

    @property
    def initialized(self) -> bool:
        return (self.data_dir / "PG_VERSION").exists()

    def dsn(self) -> str:
        return f"postgresql://{quote(self.user)}:{quote(self.password, safe='')}@127.0.0.1:{self.port}/{self.db}"

    def init_cluster(self) -> None:
        self.data_dir.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        fd, pwfile = tempfile.mkstemp(prefix="silacak-pw-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(self.password)
            r = self._run([self._exe("initdb"), "-D", str(self.data_dir), "-U", self.user,
                           "--auth=scram-sha-256", f"--pwfile={pwfile}", "-E", "UTF8", "--locale=C"])
        finally:
            try:
                os.remove(pwfile)
            except OSError:
                pass
        if r.returncode != 0:
            raise PgError(f"initdb gagal: {(r.stderr or r.stdout).strip()[-600:]}")

    def is_running(self) -> bool:
        return self._run([self._exe("pg_ctl"), "-D", str(self.data_dir), "status"]).returncode == 0

    def start(self) -> None:
        if self.is_running():  # mis. sisa proses dari sesi sebelumnya (jendela ditutup paksa): pakai lagi
            return
        r = self._run([self._exe("pg_ctl"), "-D", str(self.data_dir), "-l", str(self.log_file), "-w", "-t", "90",
                       "-o", f"-p {self.port} -c listen_addresses=127.0.0.1", "start"], quiet=True)
        if r.returncode != 0:
            tail = ""
            try:
                tail = self.log_file.read_text(errors="replace")[-600:]
            except OSError:
                pass
            raise PgError(f"PostgreSQL gagal start (kode {r.returncode}). Isi log:\n{tail}")

    def ensure_database(self) -> None:
        env = dict(os.environ, PGPASSWORD=self.password)
        r = self._run([self._exe("createdb"), "-h", "127.0.0.1", "-p", str(self.port), "-U", self.user, self.db], env=env)
        if r.returncode != 0 and "already exists" not in (r.stderr or "") + (r.stdout or ""):
            raise PgError(f"createdb gagal: {(r.stderr or r.stdout).strip()[-300:]}")

    def stop(self, wait: bool = True) -> None:
        """wait=False dipakai saat jendela konsol ditutup (Windows hanya memberi ~5 detik): cukup MEMULAI shutdown
        cepat, Postgres menyelesaikannya sendiri meski proses kita sudah mati."""
        flags = ["-w", "-t", "30"] if wait else ["-W"]
        self._run([self._exe("pg_ctl"), "-D", str(self.data_dir), "-m", "fast", *flags, "stop"], quiet=True)
