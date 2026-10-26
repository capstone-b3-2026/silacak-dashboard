"""Penyimpanan & pembacaan data pendukung dari base: baterai relay, RSSI per hop, reboot pendaki."""
from __future__ import annotations

import json

RELAY_STALE_S = 120  # relay melapor tiap ~30 dtk; 4 laporan beruntun hilang = dianggap tidak terdengar


async def insert_relay_status(conn, r: dict) -> None:
    await conn.execute(
        """INSERT INTO relay_status (relay_id, boot_id, sequence, battery_pct, volts, gauge_state,
                                     sample_age_ms, route_path, hop_count, rssi_dbm)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        r["relay_id"], r["boot_id"], r["sequence"], r["battery_pct"], r["volts"], r["gauge_state"],
        r["sample_age_ms"], r["route_path"], r["hop_count"], r["rssi_dbm"],
    )


async def insert_link_hops(conn, r: dict) -> None:
    if not r["hops"]:  # paket langsung: tidak ada RSSI per hop untuk disimpan
        return
    await conn.execute(
        "INSERT INTO link_hops (node_id, boot_id, sequence, hops) VALUES ($1,$2,$3,$4::jsonb)",
        r["node_id"], r["boot_id"], r["sequence"], json.dumps(r["hops"]),
    )


async def insert_node_boot(conn, r: dict) -> None:
    await conn.execute("INSERT INTO node_boots (node_id, boot_id) VALUES ($1,$2)", r["node_id"], r["boot_id"])


async def latest_relay_status(conn) -> list[dict]:
    """Laporan TERBARU tiap relay + nama dari tabel devices (kalau sudah didaftarkan di Setup)."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (r.relay_id)
               r.relay_id, d.name, d.plan_slot, r.battery_pct, r.volts, r.gauge_state, r.sample_age_ms,
               r.route_path, r.hop_count, r.rssi_dbm, r.received_at,
               EXTRACT(EPOCH FROM (now() - r.received_at))::int AS age_s
        FROM relay_status r
        LEFT JOIN devices d ON d.node_id = r.relay_id AND d.role = 'relay'
        ORDER BY r.relay_id, r.received_at DESC, r.id DESC
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        d["received_at"] = d["received_at"].isoformat()
        d["stale"] = d["age_s"] > RELAY_STALE_S
        out.append(d)
    return out


async def relay_history(conn, relay_id: int, hours: int, limit: int) -> list[dict]:
    rows = await conn.fetch(
        """SELECT received_at, battery_pct, volts, gauge_state, rssi_dbm, route_path
           FROM relay_status
           WHERE relay_id = $1 AND received_at > now() - make_interval(hours => $2)
           ORDER BY received_at DESC LIMIT $3""",
        relay_id, hours, limit,
    )
    return [{**dict(r), "received_at": r["received_at"].isoformat()} for r in rows]
