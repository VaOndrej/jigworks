"""JSON-lines event log. Records go through a QueueHandler; a background thread writes stdout,
so the event loop never blocks on I/O."""

from __future__ import annotations

import json
import logging
import logging.handlers
import queue
import sys
from decimal import Decimal

LOGGER_NAME = "btc_paper_trader.events"
_logger = logging.getLogger(LOGGER_NAME)
_logger.propagate = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record.msg, default=_default, separators=(",", ":"))


def _default(o: object) -> str:
    if isinstance(o, Decimal):
        return format(o, "f")
    return str(o)


def log_event(event: str, **fields: object) -> None:
    """Emit one structured event. Cheap and non-blocking; silent when logging is not set up."""
    if _logger.handlers:
        _logger.info({"event": event, **fields})


def setup_logging(stream=None) -> logging.handlers.QueueListener:
    """Install the queue handler and return the (started) listener; call ``stop()`` at exit."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    sink = logging.StreamHandler(stream or sys.stdout)
    sink.setFormatter(_JsonFormatter())
    listener = logging.handlers.QueueListener(q, sink)
    _logger.handlers.clear()
    _logger.addHandler(logging.handlers.QueueHandler(q))
    _logger.setLevel(logging.INFO)
    listener.start()
    return listener
