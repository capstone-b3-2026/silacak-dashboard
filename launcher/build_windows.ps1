# Build paket Windows dengan PyInstaller PENUH (CADANGAN, belum teruji). Jalur yang disarankan: build_portable.ps1.
# Build paket Windows. Jalankan di Windows, dari root repo:  powershell -ExecutionPolicy Bypass -File launcher\build_windows.ps1
# Prasyarat (hanya di mesin BUILD, bukan di laptop operator): Python 3.12, Node 20+, dan folder
# launcher\third_party\pgsql berisi PostgreSQL 16 "binaries" portable (harus ada bin\initdb.exe, pg_ctl.exe, createdb.exe).
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
Set-Location $root

if (-not (Test-Path "launcher\third_party\pgsql\bin\pg_ctl.exe")) {
    throw "Taruh binary PostgreSQL portable di launcher\third_party\pgsql (lihat launcher\README.md)."
}

python -m venv .build-venv
& .\.build-venv\Scripts\python.exe -m pip install --upgrade pip
& .\.build-venv\Scripts\pip.exe install -r backend\requirements.txt pyinstaller

Push-Location frontend
# repo belum punya package-lock.json -> npm ci akan gagal; pakai npm install (dan sebaiknya commit lockfile-nya)
if (Test-Path "package-lock.json") { npm ci } else { npm install }
npm run build
Pop-Location

Push-Location launcher
& ..\.build-venv\Scripts\pyinstaller.exe silacak.spec --noconfirm
Pop-Location

$out = "launcher\dist\SiLacak"
Copy-Item -Recurse -Force frontend\dist "$out\frontend"
Copy-Item -Recurse -Force launcher\third_party\pgsql "$out\pgsql"
if (Test-Path samples) { Copy-Item -Recurse -Force samples "$out\samples" }

Compress-Archive -Path $out -DestinationPath "launcher\dist\SiLacak-windows.zip" -Force
Write-Host "Selesai: launcher\dist\SiLacak-windows.zip"
