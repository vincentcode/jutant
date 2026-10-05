"""Limits how many answers are generated at once.

A small model on CPU answers one or two questions at a time; more at once only makes every
answer slower. Requests over the limit wait their turn, and are told their place in the queue.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class GenerationQueue:
    def __init__(self, limit: int):
        self.limit = limit
        self._slots = asyncio.Semaphore(limit)
        self._active = 0
        self._waiting = 0

    @property
    def busy(self) -> bool:
        return self._active >= self.limit

    def position(self) -> int:
        """The place a request arriving now would take in the queue (1 = next)."""
        return self._waiting + 1

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Wait for a free slot and hold it. Cancelling (client gone) gives it back."""
        self._waiting += 1
        try:
            await self._slots.acquire()
        finally:
            self._waiting -= 1
        self._active += 1
        try:
            yield
        finally:
            self._active -= 1
            self._slots.release()
