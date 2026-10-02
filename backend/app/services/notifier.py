import asyncio


class Notifier:
    """In-memory pub-sub sederhana buat broadcast pesan ke semua client SSE
    yang lagi connect. Cukup buat single-node deployment (mini-PC lokal),
    nggak butuh Redis/message broker eksternal."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def broadcast(self, message: str) -> None:
        for q in list(self._subscribers):
            await q.put(message)


notifier = Notifier()
