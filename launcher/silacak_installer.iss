; ============================================================================
;  SiLacak - Inno Setup installer script (T-27)
; ============================================================================
;  Membungkus paket portable hasil build_portable.ps1 (folder launcher\dist\SiLacak\)
;  menjadi satu SiLacak-Setup.exe. Pengguna tinggal unduh satu .exe, klik, pilih
;  folder, selesai. Tidak perlu ekstrak zip manual.
;
;  Cara compile (di Windows, butuh Inno Setup 6 terpasang -> ISCC.exe):
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" launcher\silacak_installer.iss
;  Dijalankan otomatis oleh build_portable.ps1 bila ISCC.exe ditemukan.
;
;  Prasyarat compile: folder launcher\dist\SiLacak\ sudah ada (jalankan
;  build_portable.ps1 lebih dulu) dan berisi SiLacak.exe + python\ + pgsql\ +
;  backend\ + frontend\.
;
;  KEPUTUSAN PENTING (lihat docs/TODO.md T-27):
;   - Per-user install (PrivilegesRequired=lowest): operator tanpa hak admin
;     tetap bisa memasang. Default ke %LOCALAPPDATA%\Programs\SiLacak.
;   - Paket TIDAK memuat .env: mode portable memakai config.json di
;     %LOCALAPPDATA%\SiLacak yang dibuat launcher saat pertama jalan. Baris
;     Excludes di bawah menjamin .env tidak ikut walau tanpa sengaja ada.
;   - Uninstaller HANYA menghapus berkas program. Data operator (database,
;     DEM, pengaturan) ada di %LOCALAPPDATA%\SiLacak dan TIDAK disentuh.
;     Tidak ada [UninstallDelete] yang menunjuk ke folder data itu.
; ============================================================================

#define AppName "SiLacak"
#define AppPublisher "Tim SiLacak"
; Versi installer. Selaraskan dengan rilis bila perlu; bisa ditimpa dari ISCC
; lewat /DAppVersion=... pada baris perintah.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

; Lokasi relatif dari berkas .iss ini (launcher\) ke akar repo.
#define RepoRoot ".."
#define PayloadDir RepoRoot + "\launcher\dist\SiLacak"
#define IconFile RepoRoot + "\frontend\public\LOGO.ico"
#define SamplesDir RepoRoot + "\samples"

[Setup]
AppId={{B2E7B6B4-6C2E-4C6E-9E2B-51AC4B5110CA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Per-user: tidak butuh admin. Operator basecamp tanpa hak admin tetap bisa pasang.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
; Izinkan pengguna mengganti folder instalasi (K butir a).
DisableDirPage=no
DisableProgramGroupPage=yes
; Output installer.
OutputDir={#RepoRoot}\launcher\dist
OutputBaseFilename=SiLacak-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Ikon aplikasi untuk installer, uninstaller, dan Add/Remove Programs.
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\SiLacak.exe
UninstallDisplayName={#AppName}
; Bahasa tampilan default; teks kustom di [Messages].
ShowLanguageDialog=no

[Languages]
Name: "id"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Opsi centang "Buat pintasan di Desktop" (K butir b). Default tercentang.
Name: "desktopicon"; Description: "Buat pintasan di Desktop"; GroupDescription: "Pintasan tambahan:"

[Files]
; Seluruh isi paket portable. Excludes menjamin .env dan artefak lokal tidak ikut.
; Seluruh paket KECUALI folder samples (sengaja: paket build berisi SEMUA DEM contoh ~50 MB;
; installer hanya perlu membawa 1-2 DEM demo agar ukuran .exe wajar). Folder samples ditambahkan
; terpisah di bawah dengan hanya berkas terpilih.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
    Excludes: "*.env,\backend\.env,__pycache__\*,*.pyc,base_link.json,app_settings.json,\samples\*"
; DEM contoh untuk operator (demo/uji unggah DEM tanpa hardware): Merapi dan Bukit Klangon.
; Diambil langsung dari repo samples/ supaya jelas berkas mana yang ikut.
Source: "{#SamplesDir}\merapi_dem.tif"; DestDir: "{app}\samples"; Flags: ignoreversion
Source: "{#SamplesDir}\klangon_dem.tif"; DestDir: "{app}\samples"; Flags: ignoreversion
; Ikon aplikasi dibawa ke folder program agar pintasan memakai logo SiLacak,
; bukan ikon Python bawaan SiLacak.exe (jaring pengaman bila exe belum di-rebuild dengan --icon).
Source: "{#IconFile}"; DestDir: "{app}"; DestName: "SiLacak.ico"; Flags: ignoreversion

[Icons]
; Start Menu (K butir b). Ikon dari LOGO.ico yang disalin ke {app}.
Name: "{group}\{#AppName}"; Filename: "{app}\SiLacak.exe"; IconFilename: "{app}\SiLacak.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop (opsional, mengikuti task desktopicon).
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SiLacak.exe"; IconFilename: "{app}\SiLacak.ico"; Tasks: desktopicon

[Run]
; Tawarkan menjalankan SiLacak setelah instalasi selesai.
Filename: "{app}\SiLacak.exe"; Description: "Jalankan {#AppName} sekarang"; Flags: nowait postinstall skipifsilent

; CATATAN: sengaja TIDAK ada bagian [UninstallDelete].
; Data operator (database Postgres, DEM, pengaturan, log) berada di
; %LOCALAPPDATA%\SiLacak -- BUKAN di {app}. Uninstaller hanya membersihkan
; berkas program yang didaftarkan di [Files]/[Icons], sehingga data operator
; tetap aman walau aplikasi di-uninstall lalu dipasang ulang.
