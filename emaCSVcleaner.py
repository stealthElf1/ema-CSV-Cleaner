
"""
Brings every study day of every alias to exactly 3 beeps (morning, noon, evening).

- Days missing at the start (day_within must begin at 1) or in between are added
  with 3 empty beeps.
- Days with fewer than 3 beeps get the missing beeps, set to the best fitting time
  of 10:00, 13:00 or 19:00. The measurements (Situation, Emotion, ...) stay empty.
- Days with more than 3 beeps keep only the 3 that are spread out the most.
- beep_within is renumbered 1-3, beep counts all beeps since the start.
- day_id, dummy_var, day and datetime of new rows are continued from the neighbouring days.

Output: one cleaned CSV file. Use it as INPUT_FILE for the alias splitter afterwards.
"""

import os
from collections import defaultdict
from datetime import timedelta
from itertools import combinations, permutations

import pandas as pd

INPUT_FILE = r"Input/EMA_DATA_54_PATIENTS.csv"
SEPERATOR = ","  # column separator in the input file
OUTPUT_FILE = r"Output/EMA_DATA_54_PATIENTS-cleansed.csv"

SLOT_HOURS = [10, 13, 19]               # morning, noon, evening
COUNTERS = ["day_id", "dummy_var", "day"]   # run up by 1 per day


def keep_most_spread(rows):
    """More than 3 beeps: keep the 3 with the largest gaps between them."""
    rows = sorted(rows, key=lambda r: r["datetime"])
    seconds = [(r["datetime"] - rows[0]["datetime"]).total_seconds() for r in rows]
    best, best_score = None, None
    for a, b, c in combinations(range(len(rows)), 3):
        gap1, gap2 = seconds[b] - seconds[a], seconds[c] - seconds[b]
        score = (min(gap1, gap2), gap1 + gap2)   # smallest gap as big as possible, then widest span
        if best_score is None or score > best_score:
            best, best_score = (a, b, c), score
    return [rows[i] for i in best]


def empty_slots(hours):
    """Match the existing beeps to different slots (closest fit overall).
    Returns the slot hours that are still empty."""
    best, best_cost = None, None
    for slots in permutations(SLOT_HOURS, len(hours)):
        cost = sum(abs(h - s) for h, s in zip(hours, slots))
        if best_cost is None or cost < best_cost:
            best, best_cost = slots, cost
    return [s for s in SLOT_HOURS if s not in best]


def process_alias(alias, records):
    days = defaultdict(list)
    for row in records:
        days[row["day_within"]].append(row)

    # for every existing day: counters and date (= date of its first beep)
    known = {}
    for day, rows in days.items():
        known[day] = {c: int(rows[0][c]) for c in COUNTERS}
        known[day]["date"] = min(r["datetime"] for r in rows).normalize()
        known[day]["early_only"] = all(r["datetime"].hour < 5 for r in rows)

    # A day with only beeps before 5:00 belongs either to that date or to the day before.
    # Decide by day_id: take the date that fits the closest normal day best.
    normal = [d for d in known if not known[d]["early_only"]]
    for day, info in known.items():
        if info["early_only"] and normal:
            ref = known[min(normal, key=lambda n: abs(n - day))]
            expected = ref["date"] + timedelta(days=info["day_id"] - ref["day_id"])
            options = [info["date"], info["date"] - timedelta(days=1)]
            info["date"] = min(options, key=lambda x: abs(x - expected))

    result = []
    for day in range(1, max(days) + 1):
        # continue the counters from the closest existing day before (or the first day)
        earlier = [d for d in known if d <= day]
        ref_day = max(earlier) if earlier else min(known)
        shift = day - ref_day                       # negative before the first day
        date = known[ref_day]["date"] + timedelta(days=int(shift))

        rows = days.get(day, [])
        if len(rows) > 3:
            rows = keep_most_spread(rows)
        elif len(rows) < 3:
            hours = [(r["datetime"] - date).total_seconds() / 3600 for r in rows]
            for hour in empty_slots(hours):
                new_row = {c: "" for c in records[0]}      # all measurements stay empty
                new_row.update(alias=alias, day_within=day,
                               datetime=date + timedelta(hours=int(hour)))
                for c in COUNTERS:
                    new_row[c] = known[ref_day][c] + shift
                rows = rows + [new_row]

        for i, row in enumerate(sorted(rows, key=lambda r: r["datetime"]), start=1):
            row["beep_within"] = i
            row["beep"] = (day - 1) * 3 + i
            result.append(row)
    return result


def main():
    df = pd.read_csv(INPUT_FILE, sep=SEPERATOR, dtype=str, keep_default_na=False)
    df = df[df["alias"].str.strip() != ""]          # skip empty rows
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["day_within"] = df["day_within"].astype(int)

    all_rows = []
    for alias, group in df.groupby("alias", sort=False):
        all_rows += process_alias(alias, group.to_dict("records"))

    result = pd.DataFrame(all_rows, columns=df.columns)
    result["datetime"] = result["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    result.to_csv(OUTPUT_FILE, sep=SEPERATOR, index=False)
    print(f"{len(df)} rows in -> {len(result)} rows out ({OUTPUT_FILE})")


if __name__ == "__main__":
    main()