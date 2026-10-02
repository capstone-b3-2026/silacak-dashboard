import re

import gpxpy
import gpxpy.gpx

from app.repositories import position_repo


def _slug(text: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")[:30]


async def build_session_gpx(conn, session_id: int) -> tuple[bytes, str] | None:
    """GPX untuk SATU sesi pendakian. Return (isi_file, nama_file), atau None kalau sesinya tidak ada."""
    s = await conn.fetchrow(
        """
        SELECT s.id, h.hiker_code, s.full_name, s.trail_name, s.checked_in_at, s.checked_out_at
        FROM hiking_sessions s JOIN hikers h ON h.id = s.hiker_id WHERE s.id = $1
        """,
        session_id,
    )
    if not s:
        return None
    points = await position_repo.get_session_track(conn, session_id)

    who = s["full_name"] or "belum check-in"
    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack(name=f"{who} ({s['hiker_code']})")
    track.description = " | ".join(
        x for x in (s["trail_name"], f"mulai {s['checked_in_at']:%Y-%m-%d %H:%M} UTC") if x
    )
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)
    for p in points:
        segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                latitude=p["lat"],
                longitude=p["lon"],
                elevation=p["elevation"],
                time=p["recorded_at"],
            )
        )

    parts = ["track", s["hiker_code"], _slug(s["full_name"]), f"{s['checked_in_at']:%Y-%m-%d}", f"s{s['id']}"]
    filename = "_".join(x for x in parts if x) + ".gpx"
    return gpx.to_xml().encode("utf-8"), filename
