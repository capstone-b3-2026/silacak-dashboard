# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec (onedir, console). BELUM DIUJI di Windows: perkirakan perlu iterasi (lihat launcher/README.md).
# Jalankan dari folder launcher/:  pyinstaller silacak.spec --noconfirm
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("rasterio", "pydantic_settings", "apscheduler", "gpxpy"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

datas += [("../backend/app/static", "app/static")]  # wizard.html (dibaca lewat path file, bukan import)
hiddenimports += collect_submodules("app")        # app.main diimpor lewat kode, tapi router/service di-import berantai
hiddenimports += collect_submodules("uvicorn")    # loop/protokol dipilih dinamis
hiddenimports += [
    "asyncpg.pgproto.pgproto",
    "serial.tools.list_ports_windows", "serial.tools.list_ports_posix",  # dipilih dinamis menurut OS
    "multipart",
]

a = Analysis(
    ["silacak_launcher.py"],
    pathex=["../backend", "."],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
# console=True SENGAJA: jendela hitam menampilkan status/error dalam bahasa Indonesia (Fase 2: ikon tray).
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SiLacak", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="SiLacak")
