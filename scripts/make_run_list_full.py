"""
Extend the sweep to EVERY combination of the six resistance levels.

The original design followed the guide's rule: balanced, or unbalanced by
changing one or two phases away from a 32 ohm base. That gave 96 load settings.
Dropping the rule and letting each phase take any level independently gives

    6 x 6 x 6 = 216 load settings

The original 96 are a strict subset of those 216, and they are already
simulated. This script writes a run list for the 120 that are NOT, so the
existing 4704 rows are reused rather than recomputed.

    216 settings x 49 PWM states = 10,584 runs total
    -  96 settings x 49          =  4,704 already done
    = 120 settings x 49          =  5,880 to simulate

New run_ids continue from 4705 so nothing collides with the existing dataset.

Writes data/run_list_extra.csv
"""

import csv
import itertools
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEVELS = [16, 24, 32, 48, 64, 96]
BASE = 32
SEED = 20260824
FIRST_NEW_ID = 4705


def original_96():
    """Reproduce exactly the load settings the first sweep used."""
    dev = [v for v in LEVELS if v != BASE]
    out = [(v, v, v) for v in LEVELS]
    for p in range(3):
        for v in dev:
            r = [BASE] * 3
            r[p] = v
            out.append(tuple(r))
    for keep in range(3):
        changed = [p for p in range(3) if p != keep]
        for v1, v2 in itertools.product(dev, repeat=2):
            r = [BASE] * 3
            r[changed[0]], r[changed[1]] = v1, v2
            out.append(tuple(r))
    return out


def pwm_states():
    def mask(s):
        m = [1] * 6
        if s:
            m[s - 1] = 0
        return m
    return [(mask(a), mask(b)) for a in range(7) for b in range(7)]


def main():
    every = list(itertools.product(LEVELS, repeat=3))
    done = original_96()

    assert len(every) == 216, len(every)
    assert len(done) == 96 and len(set(done)) == 96
    assert set(done) <= set(every), "the original 96 must be a subset of the 216"

    new = [r for r in every if r not in set(done)]
    assert len(new) == 120, len(new)

    # Shuffle the new settings but keep each one's 49 PWM states contiguous:
    # a partial sweep then still spans the space, and consecutive runs change
    # only the pulse mask rather than the network resistances.
    random.Random(SEED).shuffle(new)

    header = (["run_id", "R_a", "R_b", "R_c"]
              + [f"DG1_PWM{i}" for i in range(1, 7)]
              + [f"DG2_PWM{i}" for i in range(1, 7)]
              + ["V1_a", "V1_b", "V1_c", "I1_a", "I1_b", "I1_c",
                 "V2_a", "V2_b", "V2_c", "I2_a", "I2_b", "I2_c"])

    rows, rid = [], FIRST_NEW_ID
    for ra, rb, rc in new:
        for m1, m2 in pwm_states():
            rows.append([rid, ra, rb, rc] + m1 + m2 + [""] * 12)
            rid += 1

    out = ROOT / "data" / "run_list_extra.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    # ---- how the 216 break down, for the report ------------------------
    def kind(r):
        n = len(set(r))
        if n == 1:
            return "balanced"
        if n == 2:
            return "two phases equal"
        return "all three different"

    from collections import Counter
    all_kinds = Counter(kind(r) for r in every)
    new_kinds = Counter(kind(r) for r in new)

    print(f"all combinations   : {len(every)}  (6^3)")
    print(f"already simulated  : {len(done)}")
    print(f"to simulate now    : {len(new)}  -> {len(rows)} runs")
    print(f"run_id range       : {FIRST_NEW_ID} .. {rid-1}")
    print()
    print(f"  {'pattern':22s} {'in all 216':>11s} {'newly added':>12s}")
    for k in ("balanced", "two phases equal", "all three different"):
        print(f"  {k:22s} {all_kinds[k]:11d} {new_kinds[k]:12d}")
    print()
    print(f"  every fault class will appear {len(every)} times once merged")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
