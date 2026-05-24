"""Message debounce for WhatsApp multi-message buffering.

When customers send rapid sequential messages (3-5 within seconds),
this module buffers them in Redis and returns the combined text
after a configurable silence window (default 5 seconds).

The debounce is time-based: the timer resets on each new message.
Once no new message arrives for `window` seconds, all buffered
messages are concatenated with newlines and returned for processing.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def debounce_message(
    redis,
    conversation_id: str,
    message: str,
    window: float = 5.0,
) -> str | None:
    """Buffer a message in Redis. Returns combined text when window expires.

    Args:
        redis: async Redis client
        conversation_id: unique conversation identifier
        message: the new message text
        window: seconds to wait for more messages before processing

    Returns:
        Combined message text if this call should trigger processing,
        or None if another concurrent call will handle it.
    """
    buf_key = f"debounce:buf:{conversation_id}"
    lock_key = f"debounce:lock:{conversation_id}"

    # Append message to buffer list
    await redis.rpush(buf_key, message)
    # Safety TTL: buffer expires even if something goes wrong
    await redis.expire(buf_key, int(window + 10))

    # Wait for the silence window
    await asyncio.sleep(window)

    # Try to acquire processing lock (atomic, NX = only if not exists)
    acquired = await redis.set(lock_key, "1", nx=True, ex=15)
    if not acquired:
        # Another concurrent request is already processing this batch
        return None

    try:
        # Drain the entire buffer
        raw_messages = await redis.lrange(buf_key, 0, -1)
        await redis.delete(buf_key)

        if not raw_messages:
            return None

        # Decode and join
        texts = []
        for m in raw_messages:
            text = m.decode("utf-8") if isinstance(m, bytes) else m
            texts.append(text)

        combined = "\n".join(texts)
        logger.info(
            "Debounce: combined %d messages for conversation %s",
            len(texts), conversation_id,
        )
        return combined

    finally:
        await redis.delete(lock_key)
