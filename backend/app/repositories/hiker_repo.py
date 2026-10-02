async def get_all_hikers(conn):
    rows = await conn.fetch(
        "SELECT id, hiker_code, full_name, phone_number FROM hikers ORDER BY hiker_code"
    )
    return [dict(r) for r in rows]


async def get_hiker_by_code(conn, hiker_code: str):
    row = await conn.fetchrow(
        "SELECT id, hiker_code, full_name, phone_number FROM hikers WHERE hiker_code = $1",
        hiker_code,
    )
    return dict(row) if row else None


async def create_hiker(conn, hiker_code: str, full_name: str | None, phone_number: str | None):
    row = await conn.fetchrow(
        """
        INSERT INTO hikers (hiker_code, full_name, phone_number)
        VALUES ($1, $2, $3)
        RETURNING id, hiker_code, full_name, phone_number
        """,
        hiker_code,
        full_name,
        phone_number,
    )
    return dict(row)
