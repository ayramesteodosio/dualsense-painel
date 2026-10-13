import itertools

from PySide6.QtCore import QObject, QTimer, Signal, Slot


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        fn()


class QtLoop:
    def __init__(self):
        self._ids = itertools.count(1)
        self._timers = {}
        self._invoker = _Invoker()

    def _start(self, source, ms, fn, args, repeat):
        def fire():
            timer = self._timers.get(source)
            if timer is None:
                return
            again = fn(*args)
            if not (repeat and again):
                self.source_remove(source)

        def create():
            if source in self._timers:
                return
            timer = QTimer()
            timer.setInterval(int(ms))
            timer.timeout.connect(fire)
            self._timers[source] = timer
            timer.start()
        self._invoker.call.emit(create)
        return source

    def timeout_add(self, ms, fn, *args):
        return self._start(next(self._ids), ms, fn, args, True)

    def timeout_add_seconds(self, seconds, fn, *args):
        return self._start(next(self._ids), seconds * 1000, fn, args, True)

    def idle_add(self, fn, *args):
        return self._start(next(self._ids), 0, fn, args, False)

    def source_remove(self, source):
        def remove():
            timer = self._timers.pop(source, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()
        self._invoker.call.emit(remove)
