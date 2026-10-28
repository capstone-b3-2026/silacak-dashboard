import json


async def get_active_alert(conn, session_id: int, alert_type: str):
    row = await conn.fetchrow(
        "SELECT id FROM alerts WHERE session_id = $1 AND alert_type = $2 AND status = 'ACTIVE'",
        session_id,
        alert_type,
    )
    return dict(row) if row else None


async def create_alert(conn, hiker_id: int, session_id: int, alert_type: str, meta: dict | None = None):
    # WITH...INSERT lalu JOIN ke hikers biar hasilnya punya bentuk yang SAMA PERSIS kayak
    # list_active_alerts() (ada hiker_code, bukan cuma hiker_id) - dipakai stagnant_detector
    # buat broadcast lewat SSE, jadi alert live harus sama bentuknya dengan GET /alerts.
    row = await conn.fetchrow(
        """
        WITH new_alert AS (
            INSERT INTO alerts (hiker_id, session_id, alert_type, meta)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id, hiker_id, session_id, alert_type, status, triggered_at
        )
        SELECT na.id, h.hiker_code, na.session_id, s.full_name, na.alert_type, na.status, na.triggered_at
        FROM new_alert na
        JOIN hikers h ON h.id = na.hiker_id
        LEFT JOIN hiking_sessions s ON s.id = na.session_id
        """,
        hiker_id,
        session_id,
        alert_type,
        json.dumps(meta or {}),
    )
    return dict(row)


async def list_active_alerts(conn):
    rows = await conn.fetch(
        """
        SELECT a.id, h.hiker_code, a.session_id, s.full_name, a.alert_type, a.status, a.triggered_at
        FROM alerts a
        JOIN hikers h ON h.id = a.hiker_id
        LEFT JOIN hiking_sessions s ON s.id = a.session_id
        WHERE a.status = 'ACTIVE'
        ORDER BY a.triggered_at DESC
        """
    )
    return [dict(r) for r in rows]


async def acknowledge_alert(conn, alert_id: int):
    await conn.execute("UPDATE alerts SET status = 'ACKNOWLEDGED' WHERE id = $1", alert_id)


async def resolve_off_trail(conn, session_id: int):
    """Tandai SELESAI alarm OFF_TRAIL yang masih ACTIVE untuk sesi ini (pendaki kembali ke dalam perimeter).
    OFF_TRAIL hilang otomatis saat kembali masuk - BUKAN disenyapkan manual seperti SOS/stagnant.
    Kembalikan dict baris yang berubah (supaya pemanggil tahu perlu broadcast), atau None bila tidak ada."""
    row = await conn.fetchrow(
        """
        UPDATE alerts SET status = 'RESOLVED', resolved_at = now()
        WHERE session_id = $1 AND alert_type = 'OFF_TRAIL' AND status = 'ACTIVE'
        RETURNING id, session_id
        """,
        session_id,
    )
    return dict(row) if row else None
