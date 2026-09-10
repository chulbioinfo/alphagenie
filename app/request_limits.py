"""Bounded process-local admission controls; deployment uses one web worker."""
from collections import OrderedDict, deque
import threading
import time


class RateBudget:
    def __init__(self, per_client=30, total=120, seconds=60, max_clients=2048, clock=time.monotonic):
        self.per_client, self.total, self.seconds = per_client, total, seconds
        self.max_clients, self.clock = max_clients, clock
        self.clients, self.events = OrderedDict(), deque()
        self.lock = threading.Lock()

    def allow(self, identity):
        now = self.clock()
        cutoff = now - self.seconds
        with self.lock:
            while self.events and self.events[0] <= cutoff:
                self.events.popleft()
            for key in list(self.clients):
                queue = self.clients[key]
                while queue and queue[0] <= cutoff:
                    queue.popleft()
                if not queue:
                    del self.clients[key]
            if len(self.events) >= self.total:
                return False
            if identity not in self.clients:
                if len(self.clients) >= self.max_clients:
                    return False  # Do not evict an active identity to reset its budget.
                self.clients[identity] = deque()
            queue = self.clients[identity]
            if len(queue) >= self.per_client:
                return False
            queue.append(now)
            self.events.append(now)
            return True


RENDER_BUDGET = RateBudget(per_client=30, total=120)
FEEDBACK_BUDGET = RateBudget(per_client=20, total=100, seconds=600)
RENDER_SLOT = threading.BoundedSemaphore(1)
BODY_SLOTS = threading.BoundedSemaphore(8)


def is_render_path(path):
    import re
    return bool(re.fullmatch(r"/api/explorer/[^/]+/(?:curve\.svg|view-options|export/(?:pdf|svg|png))", path)
                or re.fullmatch(r"/api/single-variant/preset/[^/]+/(?:plot|view-options|download/plot_(?:pdf|svg|png))", path))


def is_retired_path(path):
    import re
    return path in {"/api/validate_variant", "/api/multi-variant/validate", "/api/track-selection/preview"} or bool(
        re.fullmatch(r"/(?:jobs|multi-jobs)/[^/]+/plot", path))
