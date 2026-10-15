"""Seeds a Rhythmos data folder with a week of statistics in the old single-file format (stats.json,
before 2.16), for the CI smoke test: the built app then migrates it to stats/<YYYY-MM>.json, and the
screenshots show filled statistics and past days' timelines instead of empty pages.

    python tools/seed_stats.py <data dir>      # writes <data dir>/stats.json
    python tools/seed_stats.py --check <data dir>   # exits 1 unless the migration happened
"""

import datetime as dt
import json
import os
import random
import sys


def day(seed):
    """One plausible workday: start, breaks, water, lunch, an absence, a meal pause, the finish."""
    rng = random.Random(seed)
    start = 8 * 60 + rng.randint(0, 90)
    end = start + 8 * 60 + rng.randint(-60, 60)
    lunch = 13 * 60 + rng.randint(-20, 30)
    events = [{"type": "day_start", "at": start}]
    breaks = {"done": 0, "skipped": 0}
    at = start + 20
    while at < end - 10:
        if not lunch <= at < lunch + 40:
            result = "skipped" if rng.random() < 0.15 else "done"
            breaks[result] += 1
            events.append({"type": "break", "at": at, "kind": "mini", "result": result, "sec": 30 if result == "done" else 0})
        at += 20 + rng.randint(0, 15)
    water = sorted(rng.sample(range(start + 30, end, 15), 6))
    events += [{"type": "water", "at": m} for m in water]
    events.append({"type": "meal", "at": lunch, "meal": "lunch"})
    events.append({"type": "pause", "at": lunch, "to": lunch + 40, "kind": "eating", "meal": "lunch"})
    away = start + 150 + rng.randint(0, 60)
    events.append({"type": "away", "at": away, "to": away + rng.randint(5, 25)})
    events.append({"type": "day_end", "at": end})
    events.sort(key=lambda e: e["at"])
    return {"mini_done": breaks["done"], "skipped": breaks["skipped"], "water": len(water), "water_at": water,
            "work_sec": (end - start - 40) * 60, "active_sec": breaks["done"] * 30, "meals": 1, "ate_lunch": 1,
            "ate_lunch_at": [lunch], "day_start": start, "day_end": end, "events": events}


def main(args):
    if args[0] == "--check":
        folder = args[1]
        months = os.listdir(os.path.join(folder, "stats")) if os.path.isdir(os.path.join(folder, "stats")) else []
        kept = os.path.exists(os.path.join(folder, "stats-before-2.16.json"))
        left = os.path.exists(os.path.join(folder, "stats.json"))
        print(f"stats migration: months {sorted(months)}, old file kept {kept}, stats.json left {left}")
        return 0 if months and kept and not left else 1
    folder = args[0]
    os.makedirs(folder, exist_ok=True)
    today = dt.date.today()
    data = {(today - dt.timedelta(days=back)).isoformat(): day(back) for back in range(1, 8)}
    with open(os.path.join(folder, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"seeded {len(data)} days into {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
