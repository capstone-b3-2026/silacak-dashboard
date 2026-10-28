"""SiLacak launcher: SATU klik -> database naik -> dashboard terbuka di browser.

Tidak butuh Docker, Node, nginx, atau pengaturan .env. Data pengguna ada di %LOCALAPPDATA%\\SiLacak
(atau $SILACAK_HOME), terpisah dari folder program, jadi aplikasi bisa diganti versi tanpa kehilangan data.

Jalankan dari source :  python launcher/silacak_launcher.py   (butuh PostgreSQL di PATH atau SILACAK_PG_BIN)
Hasil build Windows   :  SiLacak.exe (lihat launcher/README.md)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pgmanager import PgError, PgManager, new_password, pick_free_port, port_free  # noqa: E402

FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent


def user_home() -> Path:
    if os.environ.get("SILACAK_HOME"):
        return Path(os.environ["SILACAK_HOME"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SiLacak"
    return Path.home() / ".local" / "share" / "silacak"


def load_or_create_config(home: Path) -> dict:
    """config.json: port & password dibuat sekali, lalu dipakai terus. Pengguna tidak pernah menyentuhnya."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.json"
    cfg: dict = {}
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
    changed = False
    if not cfg.get("pg_password"):
        cfg["pg_password"], changed = new_password(), True
    if not cfg.get("web_port"):
        cfg["web_port"], changed = pick_free_port(8080, 8080, 8100), True
    if not cfg.get("pg_port"):
        cfg["pg_port"], changed = pick_free_port(), True
    cfg.setdefault("serial_port", "auto")
    if changed or not path.exists():
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def needs_wizard(home: Path) -> bool:
    """Wizard pengaturan awal tampil sampai operator menjawabnya (file dibuat saat jawaban disimpan).
    Menutup jendela tanpa menjawab TIDAK memblokir apa pun: dashboard tetap jalan dengan nilai bawaan."""
    try:
        data = json.loads((home / "data" / "app_settings.json").read_text(encoding="utf-8"))
        return not data.get("configured")
    except (OSError, ValueError, AttributeError):
        return True


def find_pg_bin() -> Path | None:
    for cand in (os.environ.get("SILACAK_PG_BIN"), str(APP_DIR / "pgsql" / "bin")):
        if cand and (Path(cand) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")).exists():
            return Path(cand)
    found = shutil.which("pg_ctl")
    return Path(found).parent if found else None


def _is_built(folder: Path) -> bool:
    """index.html hasil build memuat /assets/...; index.html SOURCE memuat /src/main.js (tidak bisa dijalankan browser)."""
    idx = folder / "index.html"
    try:
        return idx.exists() and "/src/main.js" not in idx.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def find_frontend() -> Path | None:
    # urutan penting: dist dulu. Di paket rilis isi dist ditaruh langsung di <app>/frontend.
    for cand in (APP_DIR / "frontend" / "dist", APP_DIR / "frontend"):
        if _is_built(cand):
            return cand
    return None


def is_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


_HANDLER_REFS: list = []  # handler ctypes harus tetap direferensikan, jika tidak di-GC dan proses crash


def install_console_close_handler(on_close) -> None:
    """Windows: menutup jendela konsol dengan tombol X MEMBUNUH proses tanpa menjalankan blok finally, sehingga
    Postgres ditinggal hidup (yatim). Handler ini menghentikannya dulu. Ctrl+C tetap ditangani uvicorn seperti biasa."""
    if os.name != "nt":
        return
    import ctypes

    handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    def handler(ctrl_type: int) -> int:
        if ctrl_type in (2, 5, 6):  # CTRL_CLOSE / LOGOFF / SHUTDOWN
            try:
                on_close()
            except Exception:  # noqa: BLE001
                pass
            return 1
        return 0

    ref = handler_type(handler)
    _HANDLER_REFS.append(ref)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(ref, True)


def open_window(url: str) -> None:
    """Edge --app = jendela tanpa address bar (terasa seperti aplikasi, tanpa Electron). Fallback: browser bawaan.

    --start-fullscreen menyembunyikan title bar supaya terasa seperti aplikasi native (seperti menekan F11).
    Ini BUKAN borderless sejati: operator tetap bisa keluar dengan F11 atau menutup dengan Alt+F4. Title bar
    yang benar-benar hilang (custom titlebar) butuh Electron/Tauri, tidak sepadan dan menambah dependensi besar.
    Bukan --kiosk: kiosk terlalu mengunci untuk laptop operator (tidak bisa keluar dengan mudah)."""
    if os.name == "nt":
        for edge in (shutil.which("msedge"),
                     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                     r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
            if edge and os.path.exists(edge):
                try:
                    subprocess.Popen([edge, f"--app={url}", "--start-fullscreen"])
                    return
                except OSError:
                    break
    webbrowser.open(url)


def _open_when_ready(url: str, port: int) -> None:
    for _ in range(120):
        if is_running(port):
            open_window(url)
            return
        time.sleep(0.5)


def _fail(msg: str, code: int = 1) -> int:
    print("\n" + "=" * 60 + f"\nSiLacak tidak bisa dijalankan:\n{msg}\n" + "=" * 60)
    if FROZEN:
        input("\nTekan Enter untuk menutup...")
    return code


def main() -> int:
    home = user_home()
    cfg = load_or_create_config(home)
    port = int(cfg["web_port"])
    url = f"http://127.0.0.1:{port}"

    if is_running(port):  # sudah jalan -> jangan dobel, cukup buka tampilannya
        print("SiLacak sudah berjalan. Membuka tampilan...")
        open_window(url)
        return 0
    if not port_free(port):  # port bawaan dipakai program lain
        cfg["web_port"] = port = pick_free_port(None, 8101, 8200)
        (home / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        url = f"http://127.0.0.1:{port}"

    pg_bin, frontend = find_pg_bin(), find_frontend()
    if pg_bin is None:
        return _fail("Komponen database (folder 'pgsql') tidak ditemukan di samping SiLacak.exe. Unduh ulang paket lengkapnya.")
    if frontend is None:
        if (APP_DIR / "frontend" / "index.html").exists():  # ada source, belum di-build
            return _fail("Tampilan belum di-build. Jalankan:\n  cd frontend\n  npm install\n  npm run build\nlalu buka SiLacak lagi.")
        return _fail("Komponen tampilan (folder 'frontend') tidak ditemukan. Unduh ulang paket lengkapnya.")

    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    pg = PgManager(pg_bin, home / "pgdata", logs / "postgres.log", int(cfg["pg_port"]), cfg["pg_password"])
    stopped = threading.Event()

    def stop_pg(wait: bool = True) -> None:  # idempoten: dipakai handler X maupun blok finally
        if not stopped.is_set():
            stopped.set()
            pg.stop(wait=wait)

    install_console_close_handler(lambda: stop_pg(wait=False))
    try:
        if not pg.initialized:
            print("Menyiapkan database untuk pertama kali (sekali saja)...")
            pg.init_cluster()
        if not pg.is_running() and not port_free(pg.port):  # port DB bentrok -> pindah
            pg.port = cfg["pg_port"] = pick_free_port()
            (home / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print("Menjalankan database...")
        pg.start()
        pg.ensure_database()
    except PgError as exc:
        return _fail(f"{exc}\n\nRincian ada di: {logs}")

    os.environ.update({
        "DATABASE_URL": pg.dsn(),
        "DATA_DIR": str(home / "data"),
        "FRONTEND_DIR": str(frontend),
        "SERIAL_PORT": str(cfg.get("serial_port", "auto")),
    })
    (home / "data").mkdir(parents=True, exist_ok=True)
    first_run = needs_wizard(home)
    if not FROZEN:
        sys.path.insert(0, str(APP_DIR / "backend"))

    try:
        import uvicorn
        from app.main import app  # diimpor SETELAH env di atas diset (Settings dibaca saat import)

        print("\n" + "=" * 60 + f"\n  SiLacak berjalan di {url}\n  Jangan tutup jendela ini selama dipakai.\n  Untuk berhenti: tutup jendela ini (atau Ctrl+C).\n" + "=" * 60 + "\n")
        start_url = url + ("/awal" if first_run else "")
        threading.Thread(target=_open_when_ready, args=(start_url, port), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return 0
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{type(exc).__name__}: {exc}\n\nRincian ada di: {logs}")
    finally:
        stop_pg()


if __name__ == "__main__":
    raise SystemExit(main())
