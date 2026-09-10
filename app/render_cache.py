"""Byte/count/age-bounded render cache with fail-fast single-flight admission."""
from collections import OrderedDict
import threading
import time
from fastapi import HTTPException


class RenderCache:
    def __init__(self, max_bytes=32 * 1024 * 1024, max_entries=12, ttl=300, clock=time.monotonic):
        self.max_bytes, self.max_entries, self.ttl, self.clock = max_bytes, max_entries, ttl, clock
        self.entries = OrderedDict()
        self.errors = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()
        self.slot = threading.BoundedSemaphore(1)

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.errors.clear()
            self.size = 0

    def _cached(self, key):
        now = self.clock()
        with self.lock:
            for old in list(self.entries):
                when, content = self.entries[old]
                if now - when >= self.ttl:
                    self.size -= len(content)
                    del self.entries[old]
            for old in list(self.errors):
                if now - self.errors[old][0] >= self.ttl:
                    del self.errors[old]
            if key in self.errors:
                raise HTTPException(422, self.errors[key][1])
            if key in self.entries:
                self.entries.move_to_end(key)
                return self.entries[key][1]
        return None

    def get(self, key, make):
        cached = self._cached(key)
        if cached is not None:
            return cached
        if not self.slot.acquire(blocking=False):
            raise HTTPException(503, "A figure is being prepared. Please try again shortly.", headers={"Retry-After": "2"})
        try:
            cached = self._cached(key)
            if cached is not None:
                return cached
            try:
                content = make()
            except HTTPException as exc:
                if exc.status_code == 422:
                    with self.lock:
                        self.errors[key] = (self.clock(), str(exc.detail))
                        while len(self.errors) > 128:
                            self.errors.popitem(last=False)
                raise
            with self.lock:
                if len(content) <= self.max_bytes:
                    while self.entries and (self.size + len(content) > self.max_bytes or len(self.entries) >= self.max_entries):
                        _, (_, old) = self.entries.popitem(last=False)
                        self.size -= len(old)
                    self.entries[key] = (self.clock(), content)
                    self.size += len(content)
            return content
        finally:
            self.slot.release()
