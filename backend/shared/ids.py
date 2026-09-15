"""UUID version 7 (RFC 9562): time-ordered identifiers safe to generate on offline devices."""

import os
import threading
import time
import uuid
from datetime import UTC, datetime

_MAX_COUNTER = 0xFFF
_lock = threading.Lock()
_last_ms = 0
_counter = 0


def _fresh_counter() -> int:
    # Seed with 11 random bits so the 12-bit counter has headroom within one millisecond.
    return int.from_bytes(os.urandom(2)) & 0x7FF


def uuid7() -> uuid.UUID:
    """Return a UUIDv7, strictly increasing in this process even if the clock steps back."""
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = _fresh_counter()
        else:
            _counter += 1
            if _counter > _MAX_COUNTER:
                _last_ms += 1
                _counter = _fresh_counter()
        timestamp_ms = _last_ms
        counter = _counter

    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (
        (timestamp_ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76  # version
        | counter << 64
        | 0b10 << 62  # RFC 9562 variant
        | rand_b
    )
    return uuid.UUID(int=value)


def uuid7_datetime(value: uuid.UUID) -> datetime:
    """Extract the creation time embedded in a UUIDv7."""
    if value.version != 7:
        raise ValueError(f"Not a UUIDv7: {value}")
    return datetime.fromtimestamp((value.int >> 80) / 1000, tz=UTC)
