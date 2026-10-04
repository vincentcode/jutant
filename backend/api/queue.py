"""Concurrency limiter for generations.

An asyncio.Semaphore sized by JUTANT_MAX_CONCURRENT_GENERATIONS. A waiting request receives a
`queued` event with its position first. Disconnects cancel the generation and release the slot.
"""

import asyncio


class GenerationQueue:
    def __init__(self, limit: int):
        self._semaphore = asyncio.Semaphore(limit)
        self._waiting = 0

    @property
    def waiting(self) -> int:
        return self._waiting
