"""Pengaturan yang boleh diubah operator (wizard /awal dan /pengaturan).

Sumber nilai BAWAAN = default di core/config.py (Settings), BUKAN file .env.example saat runtime: file itu
tidak ikut paket rilis dan bisa berbeda dari kode. Pilihan operator disimpan di DATA_DIR/app_settings.json:

    {"configured": true, "overrides": {"stagnant_radius_m": 80.0}}

- jawaban "Tidak"/"Tidak tahu" di wizard -> overrides kosong -> semua nilai bawaan.
- hanya kunci di FIELDS yang boleh diubah (daftar putih), dengan batas nilai, supaya API tidak bisa dipakai
  untuk mengubah DATABASE_URL, folder data, dsb.
Modul ini sengaja tanpa dependensi FastAPI/DB supaya mudah diuji.
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

log = logging.getLogger("silacak.settings")

FIELDS: list[dict[str, Any]] = [
    {
        "key": "stagnant_window_minutes", "type": "int", "min": 10, "max": 1440, "unit": "menit",
        "label": "Pendaki dianggap diam terlalu lama setelah",
        "help": "Kalau pendaki nyaris tidak berpindah selama waktu ini, sistem membunyikan alarm 'diam terlalu lama'. "
                "Nilai ini belum dikalibrasi dengan data lapangan.",
    },
    {
        "key": "stagnant_radius_m", "type": "float", "min": 5, "max": 500, "unit": "meter",
        "label": "Dianggap diam jika bergeser kurang dari",
        "help": "GPS di bawah pohon bisa meleset 10 sampai 30 meter, jadi jangan diisi terlalu kecil.",
    },
    {
        "key": "stagnant_check_interval_minutes", "type": "int", "min": 1, "max": 60, "unit": "menit",
        "label": "Sistem memeriksa pendaki diam setiap",
        "help": "Makin kecil makin cepat alarm muncul, tapi makin sering memeriksa.",
    },
]
_BY_KEY = {f["key"]: f for f in FIELDS}


def default_of(settings_cls: type, key: str) -> Any:
    """Nilai bawaan dari kelas Settings (pydantic v2 menyimpannya di model_fields)."""
    mf = getattr(settings_cls, "model_fields", None)
    if mf and key in mf:
        return mf[key].default
    return getattr(settings_cls, key)


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, "app_settings.json")


def load(data_dir: str) -> dict | None:
    """None kalau belum pernah disimpan atau file rusak."""
    try:
        with open(_path(data_dir), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def is_configured(data_dir: str) -> bool:
    saved = load(data_dir)
    return bool(saved and saved.get("configured"))


def _save(data_dir: str, overrides: dict) -> None:
    os.makedirs(data_dir, exist_ok=True)
    tmp = _path(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"configured": True, "overrides": overrides}, f, indent=2)
    os.replace(tmp, _path(data_dir))  # atomik: listrik padam di tengah tulis tidak merusak file lama


def validate(values: dict[str, Any]) -> dict[str, int | float]:
    """Cek & ubah ke tipe benar. Raise ValueError (pesan bahasa Indonesia) kalau ada yang salah."""
    out: dict[str, int | float] = {}
    for key, raw in values.items():
        meta = _BY_KEY.get(key)
        if meta is None:
            raise ValueError(f"Pengaturan '{key}' tidak dikenal.")
        msg = f"'{meta['label']}' harus berupa angka antara {meta['min']} dan {meta['max']} ({meta['unit']})."
        if isinstance(raw, bool) or raw is None:
            raise ValueError(msg)
        try:
            num = float(raw)
        except (TypeError, ValueError):
            raise ValueError(msg) from None
        if math.isnan(num) or math.isinf(num) or not (meta["min"] <= num <= meta["max"]):
            raise ValueError(msg)
        if meta["type"] == "int":
            if num != int(num):
                raise ValueError(f"'{meta['label']}' harus bilangan bulat.")
            out[key] = int(num)
        else:
            out[key] = num
    return out


def get_state(settings: Any, data_dir: str) -> dict:
    cls = type(settings)
    return {
        "configured": is_configured(data_dir),
        "fields": [
            {**f, "default": default_of(cls, f["key"]), "value": getattr(settings, f["key"])} for f in FIELDS
        ],
    }


def put_state(settings: Any, data_dir: str, mode: str, values: dict[str, Any]) -> dict:
    """mode 'default' = pakai bawaan (jawaban Tidak/Tidak tahu); 'custom' = simpan pilihan operator."""
    cls = type(settings)
    if mode == "default":
        overrides: dict = {}
        for f in FIELDS:
            setattr(settings, f["key"], default_of(cls, f["key"]))
    elif mode == "custom":
        overrides = validate(values)
        for k, v in overrides.items():
            setattr(settings, k, v)
    else:
        raise ValueError("mode harus 'default' atau 'custom'.")
    _save(data_dir, overrides)
    return get_state(settings, data_dir)


def load_saved_into(settings: Any, data_dir: str) -> None:
    """Dipanggil saat backend start: terapkan pilihan tersimpan. Nilai rusak dilewati, bukan menggagalkan start."""
    saved = load(data_dir)
    if not saved:
        return
    for key, raw in (saved.get("overrides") or {}).items():
        try:
            setattr(settings, key, validate({key: raw})[key])
        except ValueError as exc:
            log.warning("Pengaturan tersimpan dilewati: %s", exc)
