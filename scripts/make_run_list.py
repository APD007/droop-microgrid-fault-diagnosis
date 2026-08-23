"""
Build the run list for the microgrid dataset sweep.

Produces run_list.csv: one row per simulation run, 28 columns matching
Microgrid_Dataset_Schema.xlsx exactly. The OUTPUT columns (R_a..DG2_PWM6)
are filled in here; the INPUT columns (V1_a..I2_c) are left empty for the
simulation to fill.

Variation rules, as fixed by the guide:
  Resistance -- either balanced, or unbalanced by changing ONE or TWO of the
                three phases. Never all three to different values.
  PWM        -- at most one pulse open per inverter, the two inverters
                independent of each other.

Only load bank A (DG1 bus, nominal 32 ohm) is varied. Banks B and C stay at
their delivered values, so R_a/R_b/R_c is unambiguous.
"""

import csv
import itertools
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEVELS = [16, 24, 32, 48, 64, 96]   # ohm
BASE = 32                            # bank A nominal
DEVIATIONS = [v for v in LEVELS if v != BASE]
SEED = 20260821

# ---------------------------------------------------------------- loads
def load_settings():
    """96 (R_a, R_b, R_c) triples allowed by the guide's rule."""
    out = []

    # balanced: all three equal
    for v in LEVELS:
        out.append((v, v, v))

    # exactly one phase changed away from base
    for p in range(3):
        for v in DEVIATIONS:
            r = [BASE, BASE, BASE]
            r[p] = v
            out.append(tuple(r))

    # exactly two phases changed; the third stays at base.
    # the two changed phases vary independently, so equal-value pairs are
    # included (that is still "changing two of them")
    for keep in range(3):
        changed = [p for p in range(3) if p != keep]
        for v1, v2 in itertools.product(DEVIATIONS, repeat=2):
            r = [BASE, BASE, BASE]
            r[changed[0]], r[changed[1]] = v1, v2
            out.append(tuple(r))

    assert len(out) == len(set(out)), "duplicate load settings"
    return out


# ------------------------------------------------------------------ pwm
def pwm_states():
    """49 (mask1, mask2) pairs: each inverter healthy or one pulse open."""
    def mask(s):                       # s = 0 healthy, 1..6 = that pulse open
        m = [1] * 6
        if s:
            m[s - 1] = 0
        return m
    return [(mask(a), mask(b)) for a in range(7) for b in range(7)]


# ----------------------------------------------------------------- main
def main():
    loads = load_settings()
    pwms = pwm_states()

    # Shuffle the load settings but keep all 49 PWM states for a given load
    # contiguous. Two reasons: a partial sweep still covers a representative
    # spread of loads, and consecutive runs only change the pulse mask, which
    # avoids re-solving the network state space more often than necessary.
    random.Random(SEED).shuffle(loads)

    header = (["run_id", "R_a", "R_b", "R_c"]
              + [f"DG1_PWM{i}" for i in range(1, 7)]
              + [f"DG2_PWM{i}" for i in range(1, 7)]
              + ["V1_a", "V1_b", "V1_c", "I1_a", "I1_b", "I1_c",
                 "V2_a", "V2_b", "V2_c", "I2_a", "I2_b", "I2_c"])

    rows = []
    rid = 1
    for ra, rb, rc in loads:
        for m1, m2 in pwms:
            rows.append([rid, ra, rb, rc] + m1 + m2 + [""] * 12)
            rid += 1

    out = ROOT / "data" / "run_list.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    # ------------------------------------------------------ verification
    print(f"load settings : {len(loads)}")
    print(f"pwm states    : {len(pwms)}")
    print(f"total runs    : {len(rows)}")
    print(f"columns       : {len(header)}")

    bal = sum(1 for r in loads if r[0] == r[1] == r[2])
    one = sum(1 for r in loads if sum(v != BASE for v in r) == 1)
    two = sum(1 for r in loads if sum(v != BASE for v in r) == 2 and not r[0] == r[1] == r[2])
    print(f"\n  balanced          : {bal}")
    print(f"  one phase changed : {one}")
    print(f"  two phases changed: {two}")

    # every run must have at most one open pulse per inverter
    for r in rows:
        assert r[4:10].count(0) <= 1 and r[10:16].count(0) <= 1, f"bad mask in run {r[0]}"
    print("\n  mask rule (<=1 open pulse per inverter): OK on all rows")

    healthy = sum(1 for r in rows if 0 not in r[4:16])
    single = sum(1 for r in rows if r[4:16].count(0) == 1)
    double = sum(1 for r in rows if r[4:16].count(0) == 2)
    print(f"  healthy runs      : {healthy}")
    print(f"  single-fault runs : {single}")
    print(f"  double-fault runs : {double}")


if __name__ == "__main__":
    main()
