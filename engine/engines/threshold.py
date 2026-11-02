"""At what volume does a foundation model start to earn its place?

Chronos loses on this shop's data. Two explanations fit: the data is too thin,
or the benchmark is wrong. The way to tell them apart is to generate series
with a pattern that genuinely exists - weekly rhythm, a slow trend, occasional
promotions - at several volumes and lengths, and see where the model overtakes
a four-week average.

If it never wins anywhere, the harness is suspect. If it wins above some
volume, that number is a planning input: it is the point at which this part of
the system is worth switching on.
"""
import math
import random
import zlib

from engines import foundation


def make_series(days, per_day, seed=0):
    """Daily demand with a real pattern and honest Poisson noise."""
    rnd = random.Random(seed)
    out = []
    for i in range(days):
        dow = i % 7
        weekly = 1.0 + (0.35 if dow >= 5 else -0.10)          # busier at weekends
        trend = 1.0 + 0.25 * (i / max(days - 1, 1))           # slow growth
        season = 1.0 + 0.18 * math.sin(2 * math.pi * i / 30.0)  # monthly swell
        promo = 1.9 if (i % 37) < 2 else 1.0                  # occasional push
        lam = per_day * weekly * trend * season * promo
        # Poisson draw without numpy, so this stays dependency-free
        k, p, target = 0, 1.0, math.exp(-min(lam, 500))
        while p > target and k < 10000:
            k += 1
            p *= rnd.random()
        out.append(float(max(k - 1, 0)))
    return out


def sweep(volumes=(1, 3, 10, 30, 80), histories=(120, 365), series_per_cell=4,
          horizon=14, model="amazon/chronos-bolt-small", say=None):
    def log(m):
        if say:
            say(m)

    if not foundation.available():
        return {"error": "Chronos is not installed"}

    items, meta = [], {}
    for days in histories:
        for per_day in volumes:
            for s in range(series_per_cell):
                key = "v%d_d%d_s%d" % (per_day, days, s)
                # Python randomises str hashing per process, so hash(key) would make
                # this benchmark give a different answer every run. crc32 is stable.
                full = make_series(days, per_day, seed=zlib.crc32(key.encode()) % 100000)
                items.append({"id": key, "series": full[:-horizon]})
                meta[key] = {"per_day": per_day, "days": days,
                             "actual": float(sum(full[-horizon:])),
                             "train": full[:-horizon]}
    log("%d simulated series across %d volumes and %d history lengths"
        % (len(items), len(volumes), len(histories)))

    out = foundation.forecast(items, horizon, model=model, timeout=900)
    if out.get("error"):
        return {"error": out["error"]}

    cells = {}
    for key, f in (out.get("forecasts") or {}).items():
        if f.get("error"):
            continue
        m = meta[key]
        recent = m["train"][-28:]
        naive = sum(recent) / len(recent) * horizon
        cell = cells.setdefault((m["per_day"], m["days"]),
                                {"per_day": m["per_day"], "days": m["days"],
                                 "chronos": 0.0, "naive": 0.0, "n": 0, "actual": 0.0})
        cell["chronos"] += abs(f["total_p50"] - m["actual"])
        cell["naive"] += abs(naive - m["actual"])
        cell["actual"] += m["actual"]
        cell["n"] += 1

    rows = []
    for cell in cells.values():
        n = cell["n"] or 1
        c, s = cell["chronos"] / n, cell["naive"] / n
        mean_actual = cell["actual"] / n
        rows.append({"per_day": cell["per_day"], "days": cell["days"], "series": cell["n"],
                     "chronos_mae": round(c, 2), "statistics_mae": round(s, 2),
                     "chronos_error_pct": round(c / mean_actual * 100, 1) if mean_actual else None,
                     "statistics_error_pct": round(s / mean_actual * 100, 1) if mean_actual else None,
                     "winner": "chronos" if c < s else "statistics",
                     "margin_pct": round((s - c) / max(s, 1e-9) * 100, 1)})
    rows.sort(key=lambda r: (r["days"], r["per_day"]))
    wins = [r for r in rows if r["winner"] == "chronos"]
    crossover = min((r["per_day"] for r in wins), default=None)
    return {"model": model, "horizon": horizon, "rows": rows,
            "chronos_wins": len(wins), "cells": len(rows), "crossover_per_day": crossover}
