import csv
import os
import time

from . import plataforma

PATH = os.path.join(plataforma.data_dir(), "bateria.csv")
KEEP_SECONDS = 7 * 24 * 3600
MIN_INTERVAL = 300


class BatteryHistory:
    def __init__(self, path=PATH, clock=time.time):
        self.path = path
        self.clock = clock
        self.points = self._load()

    def _load(self):
        try:
            with open(self.path, newline="") as f:
                rows = [(float(t), int(p), s) for t, p, s in csv.reader(f) if p.isdigit()]
        except (OSError, ValueError):
            return []
        cutoff = self.clock() - KEEP_SECONDS
        return [r for r in rows if r[0] >= cutoff]

    def record(self, pct, status):
        if pct is None or status is None:
            return False
        now = self.clock()
        if self.points:
            t, p, s = self.points[-1]
            if p == pct and s == status and now - t < MIN_INTERVAL:
                return False
        self.points.append((now, pct, status))
        cutoff = now - KEEP_SECONDS
        if self.points[0][0] < cutoff:
            self.points = [r for r in self.points if r[0] >= cutoff]
            self._rewrite()
        else:
            self._append((now, pct, status))
        return True

    def _append(self, row):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", newline="") as f:
                csv.writer(f).writerow(row)
        except OSError:
            pass

    def _rewrite(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", newline="") as f:
                csv.writer(f).writerows(self.points)
        except OSError:
            pass

    def estimate(self):
        if len(self.points) < 2:
            return None
        status = self.points[-1][2]
        if status not in ("Charging", "Discharging"):
            return None
        segment = []
        for row in reversed(self.points):
            if row[2] != status:
                break
            segment.append(row)
        segment.reverse()
        first, last = segment[0], segment[-1]
        elapsed = (last[0] - first[0]) / 60
        delta = last[1] - first[1]
        if elapsed < 5 or delta == 0:
            return None
        rate = delta / elapsed
        if status == "Charging" and rate > 0:
            return {"kind": "full", "minutes": round((100 - last[1]) / rate)}
        if status == "Discharging" and rate < 0:
            return {"kind": "empty", "minutes": round(last[1] / -rate)}
        return None

    def as_list(self, hours=48):
        cutoff = self.clock() - hours * 3600
        return [[round(t * 1000), p, s] for t, p, s in self.points if t >= cutoff]
