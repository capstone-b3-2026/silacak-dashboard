import json

from app.core import database
from app.core.config import settings
from app.repositories import alert_repo, position_repo
from app.services.geo import choose_window_minutes, dist_point_to_trail_m
from app.services.notifier import notifier


async def check_stagnant_hikers() -> None:
    """Dijalankan berkala oleh scheduler (lihat core/scheduler.py).
    Cek siapa aja yang diam di radius yang sama selama window tertentu,
    lalu buat alert kalau belum ada alert STAGNANT yang masih aktif
    (biar nggak spam alert baru tiap kali job jalan).

    Window-nya ADAPTIF terhadap koridor jalur (lihat config.py):
    - Posisi terakhir pendaki di DALAM koridor (<= stagnant_perimeter_m dari trail)
      -> diam dianggap wajar (istirahat/tidur), window panjang (inside).
    - Di LUAR koridor (menyimpang) -> diam mencurigakan (kecelakaan), window pendek (outside).

    Kalau lokasi aktif belum punya jalur (< 2 titik trail), deteksi stagnan DILEWATI
    seluruhnya: belum ada acuan koridor. SOS manual dari hardware (sos_watch.py) jalur terpisah
    dan tidak terpengaruh."""
    async with database.pool.acquire() as conn:
        trail = await position_repo.get_active_site_trail(conn)
        if len(trail) < 2:
            # Belum ada jalur acuan -> jangan menebak; biarkan SOS manual yang bekerja.
            return

        trail_pts = [(p[0], p[1]) for p in trail]  # (lat, lon), LAT DULU - jangan ditukar
        sessions = await position_repo.get_active_sessions_latest_position(conn)

        # Hitung jarak tiap sesi ke trail + window yang berlaku. Kelompokkan per window
        # supaya find_stagnant_sessions dipanggil sekali per window (bukan per sesi).
        info_by_session: dict[int, dict] = {}
        sessions_by_window: dict[int, set[int]] = {}
        for s in sessions:
            dist_m = dist_point_to_trail_m((s["lat"], s["lon"]), trail_pts)
            inside = dist_m <= settings.stagnant_perimeter_m
            window = choose_window_minutes(
                dist_m,
                settings.stagnant_perimeter_m,
                settings.stagnant_window_inside_minutes,
                settings.stagnant_window_outside_minutes,
            )
            info_by_session[s["session_id"]] = {
                "dist_to_trail_m": round(dist_m, 1),
                "inside": inside,
                "window_minutes": window,
            }
            sessions_by_window.setdefault(window, set()).add(s["session_id"])

        for window, session_ids in sessions_by_window.items():
            stagnant = await position_repo.find_stagnant_sessions(
                conn,
                window_minutes=window,
                radius_m=settings.stagnant_radius_m,
            )
            for row in stagnant:
                # Sesi ini diam menurut window X; pakai hanya kalau window X memang
                # yang dipilih untuknya (sesi dengan window lain diperiksa di iterasi lain).
                if row["session_id"] not in session_ids:
                    continue

                existing = await alert_repo.get_active_alert(conn, row["session_id"], "STAGNANT")
                if existing:
                    continue

                info = info_by_session[row["session_id"]]
                alert = await alert_repo.create_alert(
                    conn,
                    row["hiker_id"],
                    row["session_id"],
                    "STAGNANT",
                    meta={
                        "radius_m": settings.stagnant_radius_m,
                        "window_minutes": info["window_minutes"],
                        "perimeter_m": settings.stagnant_perimeter_m,
                        "dist_to_trail_m": info["dist_to_trail_m"],
                        "inside": info["inside"],
                    },
                )
                await notifier.broadcast(
                    json.dumps({"type": "alert", "data": alert}, default=str)
                )
