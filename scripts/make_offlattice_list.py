"""
Build a held-out validation run list at resistances the model has NEVER seen.

The training set uses six levels, {16, 24, 32, 48, 64, 96} ohm. A tree model
predicts piecewise-constant values, so there is a real risk it has learned to
snap to the nearest trained level rather than genuinely interpolating. If the
guide tests with, say, 40 ohm, that would show up immediately.

This list uses only OFF-LATTICE values - 20, 40, 56, 72, 88 - none of which
appear anywhere in training. Same 49 PWM states per load setting, so the fault
head is exercised too.

12 load settings x 49 states = 588 runs, roughly 11 minutes on four workers.

Writes data/run_list_offlattice.csv
"""

import csv
import itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRAINED = {16, 24, 32, 48, 64, 96}          # must not appear below
OFF = [20, 40, 56, 72, 88]
BASE = 32                                    # the untouched reference phase

# Deliberately spans all three patterns the guide permits, so the off-lattice
# test is not just the easy balanced case.
LOADS = [
    (20, 20, 20), (40, 40, 40), (72, 72, 72),          # balanced, off-lattice
    (20, 32, 32), (32, 40, 32), (32, 32, 72), (88, 32, 32),   # one changed
    (20, 40, 32), (32, 56, 72), (40, 32, 20), (72, 20, 32), (56, 72, 32),
]


def pwm_states():
    def mask(s):
        m = [1] * 6
        if s:
            m[s - 1] = 0
        return m
    return [(mask(a), mask(b)) for a in range(7) for b in range(7)]


def main():
    # a balanced off-lattice triple is allowed to sit away from BASE; every
    # other triple must keep exactly one phase at BASE, matching the rule
    for r in LOADS:
        assert len(set(r) - TRAINED - {BASE}) > 0 or len(set(r)) == 1, \
            f"{r} contains no off-lattice value"
        for v in r:
            if v != BASE:
                assert v not in TRAINED, f"{r} uses trained level {v}"

    header = (["run_id", "R_a", "R_b", "R_c"]
              + [f"DG1_PWM{i}" for i in range(1, 7)]
              + [f"DG2_PWM{i}" for i in range(1, 7)]
              + ["V1_a", "V1_b", "V1_c", "I1_a", "I1_b", "I1_c",
                 "V2_a", "V2_b", "V2_c", "I2_a", "I2_b", "I2_c"])

    rows, rid = [], 1
    for ra, rb, rc in LOADS:
        for m1, m2 in pwm_states():
            rows.append([rid, ra, rb, rc] + m1 + m2 + [""] * 12)
            rid += 1

    out = ROOT / "data" / "run_list_offlattice.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    used = sorted({v for r in LOADS for v in r})
    print(f"load settings : {len(LOADS)}")
    print(f"pwm states    : {len(pwm_states())}")
    print(f"total runs    : {len(rows)}")
    print(f"levels used   : {used}")
    print(f"overlap with training levels: "
          f"{sorted(set(used) & TRAINED)}  (32 is the untouched reference phase)")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
