import heapq
import itertools
import threading
import time


class GLibLoop:
    def __init__(self):
        from gi.repository import GLib
        self._glib = GLib

    def timeout_add(self, ms, fn, *args):
        return self._glib.timeout_add(int(ms), fn, *args)

    def timeout_add_seconds(self, seconds, fn, *args):
        return self._glib.timeout_add_seconds(int(seconds), fn, *args)

    def idle_add(self, fn, *args):
        return self._glib.idle_add(fn, *args)

    def source_remove(self, source):
        try:
            self._glib.source_remove(source)
        except Exception:
            pass


class ThreadLoop:
    def __init__(self):
        self._timers = []
        self._ids = itertools.count(1)
        self._cancelled = set()
        self._cond = threading.Condition()
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="dualsense-loop", daemon=True)
        self._thread.start()

    def stop(self):
        with self._cond:
            self._running = False
            self._cond.notify_all()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def in_loop(self):
        return threading.current_thread() is self._thread

    def _schedule(self, delay, interval, fn, args):
        source = next(self._ids)
        with self._cond:
            heapq.heappush(self._timers, (time.monotonic() + delay, source, interval, fn, args))
            self._cond.notify_all()
        return source

    def timeout_add(self, ms, fn, *args):
        return self._schedule(ms / 1000, ms / 1000, fn, args)

    def timeout_add_seconds(self, seconds, fn, *args):
        return self._schedule(seconds, seconds, fn, args)

    def idle_add(self, fn, *args):
        return self._schedule(0, None, fn, args)

    def source_remove(self, source):
        with self._cond:
            self._cancelled.add(source)

    def call_sync(self, fn, *args, timeout=5):
        if self.in_loop():
            return fn(*args)
        done = threading.Event()
        box = {}

        def run():
            try:
                box["value"] = fn(*args)
            except Exception as e:
                box["error"] = e
            done.set()
            return False
        self.idle_add(run)
        done.wait(timeout)
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _run(self):
        while True:
            with self._cond:
                while self._running and (not self._timers or self._timers[0][0] > time.monotonic()):
                    wait = self._timers[0][0] - time.monotonic() if self._timers else None
                    self._cond.wait(wait)
                if not self._running:
                    return
                due, source, interval, fn, args = heapq.heappop(self._timers)
                if source in self._cancelled:
                    self._cancelled.discard(source)
                    continue
            try:
                again = fn(*args)
            except Exception:
                import traceback
                traceback.print_exc()
                again = False
            if again and interval is not None:
                with self._cond:
                    if source in self._cancelled:
                        self._cancelled.discard(source)
                    else:
                        heapq.heappush(self._timers, (max(due + interval, time.monotonic()), source, interval, fn, args))
