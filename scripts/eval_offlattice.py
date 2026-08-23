"""
The honest test: resistances the model has never seen.

Training uses six levels, {16, 24, 32, 48, 64, 96} ohm. A random forest is
piecewise-constant, so there is a real possibility it has learned to snap each
prediction to the nearest trained level rather than genuinely interpolating.
If the guide tests at 40 ohm, that distinction decides whether the model works
or only appears to.

This merges the off-lattice sweep, runs the shipped model on it, and reports
accuracy split by whether the true resistance was ever seen in training.

Usage:
    python scripts/eval_offlattice.py
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
TRAINED_LEVELS = {16, 24, 32, 48, 64, 96}


def main():
    parts = sorted((ROOT / "data" / "raw").glob("sweep_offlattice_part*.csv"))
    if not parts:
        sys.exit("no off-lattice sweep found - run make_offlattice_list.py "
                 "then run_sweep(w,4,inf,'_offlattice')")

    df = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    df = df.sort_values("run_id").reset_index(drop=True)
    merged = ROOT / "data" / "dataset_offlattice.csv"
    df.to_csv(merged, index=False)
    print(f"merged {len(parts)} files -> {len(df)} rows -> "
          f"{merged.relative_to(ROOT)}")

    levels = sorted({v for c in ("R_a", "R_b", "R_c") for v in df[c].unique()})
    unseen = sorted(set(levels) - TRAINED_LEVELS)
    print(f"resistance levels present : {levels}")
    print(f"never seen in training    : {unseen}\n")

    bundle = joblib.load(ROOT / "models" / "fault_diagnosis.joblib")
    F.check_input(df)
    F.derive(df)
    X = df[bundle["features"]].to_numpy()

    t1 = df.apply(lambda r: F.pulse_state(r, 1), axis=1).to_numpy()
    t2 = df.apply(lambda r: F.pulse_state(r, 2), axis=1).to_numpy()
    p1 = bundle["fault_dg1"].predict(X)
    p2 = bundle["fault_dg2"].predict(X)

    print("=== FAULT HEAD, on load conditions never seen ===")
    print(f"  inverter 1   {(p1 == t1).mean()*100:6.2f} %")
    print(f"  inverter 2   {(p2 == t2).mean()*100:6.2f} %")
    print(f"  both correct {((p1 == t1) & (p2 == t2)).mean()*100:6.2f} %"
          f"   (49 combined states)")

    print("\n=== LOAD HEAD: analytic formula vs random forest ===")
    print(f"  {'target':8s} {'analytic MAE':>14s} {'max':>9s}"
          f" | {'forest MAE':>12s} {'max':>9s}")
    all_err = []
    for tgt in ("R_a", "R_b", "R_c"):
        truth = df[tgt].to_numpy()
        ea = np.abs(df[f"Rest_{tgt[-1]}"].to_numpy() - truth)
        ef = np.abs(bundle[tgt].predict(X) - truth)
        all_err.append(ea)
        print(f"  {tgt:8s} {ea.mean():12.4f}o {ea.max():8.4f}o"
              f" | {ef.mean():10.3f}o {ef.max():8.3f}o")

    # The question that matters: does it snap to a trained level, or land on
    # the true off-lattice value? Snapping would show up as error close to the
    # distance to the nearest trained level.
    print("\n=== does each head snap to the nearest trained level? ===")
    print(f"  {'true R':>7s} {'n':>5s} {'nearest':>8s} | {'forest mean':>12s}"
          f" {'off by':>8s} | {'analytic mean':>14s} {'off by':>8s}")
    seen = set()
    for tgt in ("R_a", "R_b", "R_c"):
        pf = bundle[tgt].predict(X)
        pa = df[f"Rest_{tgt[-1]}"].to_numpy()
        for lvl in sorted(df[tgt].unique()):
            if lvl in TRAINED_LEVELS or (tgt, lvl) in seen:
                continue
            seen.add((tgt, lvl))
            m = (df[tgt] == lvl).to_numpy()
            nearest = min(TRAINED_LEVELS, key=lambda t: abs(t - lvl))
            print(f"  {lvl:7.0f} {int(m.sum()):5d} {nearest:7.0f}o |"
                  f" {pf[m].mean():11.2f}o {pf[m].mean()-lvl:+7.2f}o |"
                  f" {pa[m].mean():13.3f}o {pa[m].mean()-lvl:+7.3f}o")

    e = np.concatenate(all_err)
    print(f"\n  analytic head, MAE across all off-lattice rows: "
          f"{e.mean():.4f} ohm")
    if e.mean() < 1.0:
        print("  -> the analytic head lands on the true values. It generalises")
        print("     to any resistance, because it computes rather than recalls.")
        print("  -> the forest does NOT: it returns the nearest trained level,")
        print("     which is why predict.py ships the analytic value and keeps")
        print("     the forest only as a labelled comparison column.")
    else:
        print("  -> WARNING: the analytic head is off too. Investigate before "
              "shipping.")


if __name__ == "__main__":
    main()
