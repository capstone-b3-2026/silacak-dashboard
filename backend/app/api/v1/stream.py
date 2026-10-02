import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.notifier import notifier

router = APIRouter(tags=["stream"])


@router.get("/stream")
async def stream():
    """Server-Sent Events: push posisi baru & alert baru ke dashboard
    secara real-time. Dipilih daripada WebSocket karena komunikasinya
    memang cuma satu arah (server -> client) dan SSE auto-reconnect
    bawaan browser (EventSource), jadi lebih simpel & ringan."""
    queue = notifier.subscribe()

    async def event_generator():
        try:
            while True:
                message = await queue.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            notifier.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
