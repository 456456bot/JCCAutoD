"""Coalesce previews while giving stop, error and purchase events priority."""

import queue
import threading


class UiMessages:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self.previews = {}
        self.lock = threading.Lock()

    def put(self, item):
        kind, value, _ = item
        if kind == "result" or (kind == "search" and not value[2]):
            with self.lock:
                self.previews[kind] = item
        else:
            self.events.put(item)

    def get_nowait(self):
        try:
            return self.events.get_nowait()
        except queue.Empty:
            with self.lock:
                if not self.previews:
                    raise
                key = next(iter(self.previews))
                return self.previews.pop(key)
