"""
Merge the per-worker sweep files, validate them, and emit the deliverables.

Reads   sweep_part*.csv          (one per MATLAB worker, 42 columns each)
Writes  dataset.csv              28 columns - the schema exactly as fixed
        dataset_extended.csv     34 columns - adds the 6 DC-offset features
        diagnostics.csv          per-run health record, not dataset columns

Both dataset files come from the same runs. Which one you hand in depends on
your guide's answer about the 6 extra columns; nothing needs re-simulating
either way.
"""

import csv
import glob
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

N_EXPECTED = 4704

SCHEMA_28 = (["run_id", "R_a", "R_b", "R_c"]
             + [f"DG1_PWM{i}" for i in range(1, 7)]
             + [f"DG2_PWM{i}" for i in range(1, 7)]
             + ["V1_a", "V1_b", "V1_c", "I1_a", "I1_b", "I1_c",
                "V2_a", "V2_b", "V2_c", "I2_a", "I2_b", "I2_c"])

EXTRA_6 = ["I1mean_a", "I1mean_b", "I1mean_c",
           "I2mean_a", "I2mean_b", "I2mean_c"]

# fundamental phasor: magnitude and angle. Needed for the load task - the
# resistance cannot be recovered under fault from magnitudes alone, because
# the two inverters' currents must be summed as phasors.
PHASOR_24 = ([f"{s}f_{p}" for s in ("V1", "I1", "V2", "I2") for p in "abc"]
             + [f"{s}ang_{p}" for s in ("V1", "I1", "V2", "I2") for p in "abc"])

DIAG = ["run_id", "f1", "f2", "P1", "P2", "Q1", "Q2", "wall_s", "ok"]

# plausible ranges - anything outside these is flagged, not silently kept
RANGES = {
    "V1": (50.0, 600.0), "V2": (50.0, 600.0),
    "I1": (0.0, 200.0), "I2": (0.0, 200.0),
    "f1": (48.0, 52.0), "f2": (48.0, 52.0),
}


def load():
    parts = sorted(glob.glob(str(ROOT / "data" / "raw" / "sweep_part*.csv")))
    if not parts:
        sys.exit("no sweep_part*.csv in data/raw - has the sweep run?")
    rows = {}
    for p in parts:
        with open(p, newline="") as f:
            n = 0
            for r in csv.DictReader(f):
                rows[int(float(r["run_id"]))] = r      # later file wins
                n += 1
        print(f"  {Path(p).name:24s} {n:5d} rows")
    return rows


def check(rows):
    problems = []

    missing = [i for i in range(1, N_EXPECTED + 1) if i not in rows]
    if missing:
        problems.append(f"{len(missing)} runs missing "
                        f"(first few: {missing[:10]})")

    extra = [i for i in rows if not 1 <= i <= N_EXPECTED]
    if extra:
        problems.append(f"{len(extra)} unexpected run_ids: {extra[:10]}")

    failed = [i for i, r in rows.items() if r.get("ok", "1").strip() not in ("1", "1.0")]
    if failed:
        problems.append(f"{len(failed)} runs reported ok=0: {failed[:10]}")

    nan_rows, oor = [], []
    for i, r in sorted(rows.items()):
        for col in SCHEMA_28[16:] + EXTRA_6 + PHASOR_24 + ["f1", "f2"]:
            try:
                v = float(r[col])
            except (KeyError, ValueError, TypeError):
                nan_rows.append((i, col))
                continue
            if math.isnan(v) or math.isinf(v):
                nan_rows.append((i, col))
                continue
            lo_hi = RANGES.get(col.split("_")[0] if "_" in col else col)
            if lo_hi and not lo_hi[0] <= abs(v) <= lo_hi[1]:
                oor.append((i, col, v))

    if nan_rows:
        problems.append(f"{len(nan_rows)} NaN/missing values "
                        f"(first: {nan_rows[:5]})")
    if oor:
        problems.append(f"{len(oor)} values outside plausible range "
                        f"(first: {oor[:5]})")
    return problems


def write(path, cols, rows):
    path = ROOT / "data" / path
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in sorted(rows):
            w.writerow([rows[i].get(c, "") for c in cols])
    print(f"  wrote data/{path.name:20s} {len(rows):5d} rows x {len(cols)} cols")


def main():
    print("reading worker files:")
    rows = load()
    print(f"\n{len(rows)} unique runs (expected {N_EXPECTED})\n")

    problems = check(rows)
    if problems:
        print("VALIDATION PROBLEMS:")
        for p in problems:
            print("  !", p)
        print()
    else:
        print("validation: all runs present, converged, in range\n")

    print("writing:")
    write("dataset.csv", SCHEMA_28, rows)
    write("dataset_extended.csv", SCHEMA_28 + EXTRA_6, rows)
    write("dataset_full.csv", SCHEMA_28 + EXTRA_6 + PHASOR_24, rows)
    write("diagnostics.csv", DIAG, rows)

    times = [float(r["wall_s"]) for r in rows.values() if r.get("wall_s")]
    if times:
        print(f"\nsimulation time: {sum(times)/3600:.2f} h total, "
              f"{sum(times)/len(times):.1f} s/run mean")


if __name__ == "__main__":
    main()
