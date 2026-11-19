"""Building and emitting contract-valid `RunEvent`s.

Every event the runner produces goes through `EventSink.emit`, which fills the run-level
fields (runId, release, digest, seq, at), validates the event against the frozen contract
(`jigworks_contracts.validate("RunEvent", …)`) and hands it to the subscribers.
`seq` counts from 0 without gaps per run (packages/contracts/README.md).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import jigworks_contracts as contracts

Event = dict[str, Any]
Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InvalidEvent(ValueError):
    pass


@dataclass
class EventSink:
    run_id: str
    release: str | None = None
    digest: str | None = None
    clock: Clock = utcnow
    next_seq: int = 0
    subscribers: list[Callable[[Event], None]] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    keep: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self.subscribers.append(fn)

    def now(self) -> str:
        return iso(self.clock())

    def emit(self, kind: str, *, node: str | None = None, attempt: int | None = None, **fields: Any) -> Event:
        with self._lock:
            event: Event = {"runId": self.run_id, "seq": self.next_seq, "kind": kind, "at": self.now()}
            if self.release:
                event["release"] = self.release
            if self.digest:
                event["digest"] = self.digest
            if node is not None:
                event["node"] = node
            if attempt is not None:
                event["attempt"] = attempt
            event.update({k: v for k, v in fields.items() if v is not None})
            errors = contracts.validate("RunEvent", event)
            if errors:
                raise InvalidEvent(f"runner built an invalid RunEvent ({kind}): {'; '.join(errors)}")
            self.next_seq += 1
            if self.keep:
                self.events.append(event)
        for fn in self.subscribers:
            fn(event)
        return event


@dataclass(frozen=True)
class NodeContext:
    """Where an agent call belongs: the sink of the run plus the node and attempt."""

    sink: EventSink
    node: str
    attempt: int = 1

    def emit(self, kind: str, **fields: Any) -> Event:
        return self.sink.emit(kind, node=self.node, attempt=self.attempt, **fields)
