"""WebSocket fan-out with a bounded queue per client.

``Broadcaster.publish`` is synchronous and never awaits, so a slow client can never delay the
exchange or other clients. Per client:

* ``book`` / ``reference`` / ``candle:<source>:<tf>`` keep only the newest message (coalesced);
* ``trade`` keeps the newest 100;
* ``fill`` / ``state`` are never dropped; more than 1,000 waiting closes the socket with 1013.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque

MUST_DELIVER = ("fill", "state")
TRADES_KEPT = 100
MUST_LIMIT = 1000
CLOSE_OVERLOAD = 1013


class Shared(dict):
    """A published message. Every client queue holds the same object, so it is encoded once."""

    __slots__ = ("_text",)

    def text(self) -> str:
        try:
            return self._text
        except AttributeError:
            self._text = json.dumps(self, separators=(",", ":"))
            return self._text


class ClientQueue:
    def __init__(self, account_id: str, tf: str = "1m") -> None:
        self.account_id = account_id
        self.tf = tf
        self.closed = False
        self.close_code: int | None = None
        self._must: deque[dict] = deque()
        self._slots: dict[object, dict] = {}  # coalesced messages and trades, in arrival order
        self._trade_keys: deque[object] = deque()
        self._trade_seq = 0
        self._event = asyncio.Event()

    def push(self, msg: dict) -> None:
        if self.closed:
            return
        kind = msg.get("type")
        if kind in MUST_DELIVER:
            self._must.append(msg)
            if len(self._must) > MUST_LIMIT:
                self.closed = True
                self.close_code = CLOSE_OVERLOAD
        elif kind == "trade":
            self._trade_seq += 1
            key = ("trade", self._trade_seq)
            self._slots[key] = msg
            self._trade_keys.append(key)
            if len(self._trade_keys) > TRADES_KEPT:
                self._slots.pop(self._trade_keys.popleft(), None)
        else:
            key = (kind, msg.get("source"), msg.get("tf")) if kind == "candle" else kind
            self._slots.pop(key, None)  # re-insert so the newest message is also the latest in order
            self._slots[key] = msg
        self._event.set()

    def drain(self) -> list[dict]:
        """Waiting messages, must-deliver first, then the rest in arrival order."""
        out = [*self._must, *self._slots.values()]
        self._must.clear()
        self._slots.clear()
        self._trade_keys.clear()
        self._event.clear()
        return out

    async def wait(self) -> None:
        await self._event.wait()

    def pending(self) -> bool:
        return bool(self._must or self._slots)

    def must_pending(self) -> bool:
        return bool(self._must)


class Broadcaster:
    def __init__(self) -> None:
        self._clients: dict[ClientQueue, None] = {}
        self._by_account: dict[str, dict[ClientQueue, None]] = {}

    def register(self, account_id: str, tf: str = "1m") -> ClientQueue:
        q = ClientQueue(account_id, tf)
        self._clients[q] = None
        self._by_account.setdefault(account_id, {})[q] = None
        return q

    def unregister(self, q: ClientQueue) -> None:
        self._clients.pop(q, None)
        group = self._by_account.get(q.account_id)
        if group is not None:
            group.pop(q, None)
            if not group:
                del self._by_account[q.account_id]
        q.closed = True

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def has_account(self, account_id: str) -> bool:
        return account_id in self._by_account

    def publish(self, msg: dict, account_id: str | None = None) -> None:
        msg = Shared(msg)
        kind = msg.get("type")
        if kind in MUST_DELIVER:
            if account_id is not None:
                for q in self._by_account.get(account_id, ()):
                    q.push(msg)
            return
        if kind == "candle":
            tf = msg.get("tf")
            for q in self._clients:
                if q.tf == tf:
                    q.push(msg)
            return
        for q in self._clients:
            q.push(msg)
