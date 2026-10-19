# Build paket PORTABLE "Python bawaan" (disarankan). Jalankan di Windows, dari root repo:
#   powershell -ExecutionPolicy Bypass -File launcher\build_portable.ps1
# Prasyarat di mesin BUILD saja (butuh internet): Python 3.12 terpasang (untuk membekukan pemicu kecil), frontend sudah di-build
#   (frontend\dist), dan PostgreSQL portable di launcher\third_party\pgsql (harus ada bin\pg_ctl.exe, initdb.exe, createdb.exe).
# $PythonVersion HARUS 3.12.x: requirements.txt dikunci ke wheel cp312.
param(
    [string]$PythonVersion = "3.12.8",
    [string]$PgDir = "launcher\third_party\pgsql"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest di PowerShell 5.1 sangat lambat bila progress bar menyala
$root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $root

if (-not (Test-Path "$PgDir\bin\pg_ctl.exe")) { throw "Taruh binary PostgreSQL portable di $PgDir (harus ada bin\pg_ctl.exe)." }
if (-not (Test-Path "frontend\dist\index.html")) { throw "Build frontend dulu: cd frontend; npm install; npm run build" }

$out = Join-Path $root "launcher\dist\SiLacak"
$tmp = Join-Path $root "launcher\dist\_work"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force -Path "$out\python", $tmp | Out-Null

Write-Host "1/7 Mengunduh Python embeddable $PythonVersion ..."
Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile "$tmp\python-embed.zip"
Expand-Archive "$tmp\python-embed.zip" -DestinationPath "$out\python" -Force

Write-Host "2/7 Mengaktifkan site-packages ..."
$pth = Get-ChildItem "$out\python" -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem "$out\python" -Filter "python*.zip" | Select-Object -First 1).Name
New-Item -ItemType Directory -Force -Path "$out\python\Lib\site-packages" | Out-Null
@($zipName, ".", "Lib\site-packages", "..\backend", "..\launcher", "import site") | Set-Content $pth.FullName -Encoding ASCII

Write-Host "3/7 Memasang pip ..."
Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile "$tmp\get-pip.py"
$py = "$out\python\python.exe"
& $py "$tmp\get-pip.py" --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip gagal" }

Write-Host "4/7 Memasang pustaka backend (beberapa menit) ..."
& $py -m pip install -r backend\requirements.txt --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "pip install gagal" }

Write-Host "5/7 Menyalin aplikasi ..."
New-Item -ItemType Directory -Force -Path "$out\backend", "$out\launcher" | Out-Null
Copy-Item -Recurse backend\app "$out\backend\app"
Copy-Item -Recurse backend\scripts "$out\backend\scripts"
Copy-Item launcher\silacak_launcher.py, launcher\pgmanager.py "$out\launcher\"
Copy-Item -Recurse frontend\dist "$out\frontend"
Copy-Item -Recurse $PgDir "$out\pgsql"
if (Test-Path samples) { Copy-Item -Recurse samples "$out\samples" }
Get-ChildItem "$out\backend" -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

Write-Host "6/7 Uji impor (menangkap pustaka yang kurang SEKARANG, bukan di laptop operator) ..."
$env:DATA_DIR = "$tmp\data"
& $py -c "import app.main, rasterio, scipy, serial, asyncpg, uvicorn, apscheduler; print('impor OK')"
if ($LASTEXITCODE -ne 0) { throw "Uji impor gagal: ada pustaka yang kurang atau tidak cocok." }

Write-Host "7/7 Membuat SiLacak.exe (pemicu kecil) ..."
python -m venv "$tmp\venv"
& "$tmp\venv\Scripts\pip.exe" install pyinstaller
& "$tmp\venv\Scripts\pyinstaller.exe" launcher\stub\run_silacak.py --onefile --console --name SiLacak `
    --distpath $out --workpath "$tmp\pyi" --specpath $tmp --noconfirm
if (-not (Test-Path "$out\SiLacak.exe")) { throw "SiLacak.exe tidak terbentuk" }

Compress-Archive -Path $out -DestinationPath "launcher\dist\SiLacak-windows.zip" -Force
Write-Host "Selesai: launcher\dist\SiLacak-windows.zip  (uji: ekstrak ke folder BARU lalu klik SiLacak.exe)"
