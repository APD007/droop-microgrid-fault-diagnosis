"""
Train the model that ships, and save it.

Different from train_model.py, which exists to COMPARE feature sets and
therefore holds out a quarter of the data to measure honestly. This script
trains the final model on ALL 4704 rows - the held-out numbers are already
measured and reported, and the delivered model should use every row available.

Saves one bundle, models/fault_diagnosis.joblib, containing the five fitted
estimators, the exact feature list they expect, and provenance metadata.
Everything needed to reproduce a prediction travels in one file.

Usage:
    python scripts/train_final.py [path/to/dataset_full.csv]
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260823
N_TREES = 400          # more than the 300 used for comparison; this one ships


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "unknown"


def main():
    path = (Path(sys.argv[1]) if len(sys.argv) > 1
            else ROOT / "data" / "dataset_full.csv")
    if not path.exists():
        sys.exit(f"no dataset at {path}")

    df = pd.read_csv(path)
    F.check_input(df)
    F.derive(df)

    df["dg1_state"] = df.apply(lambda r: F.pulse_state(r, 1), axis=1)
    df["dg2_state"] = df.apply(lambda r: F.pulse_state(r, 2), axis=1)

    X = df[F.MODEL_FEATURES].to_numpy()
    print(f"training on {len(df)} rows x {len(F.MODEL_FEATURES)} features")
    print(f"  {len(F.REQUIRED_INPUT)} measured + {len(F.DERIVED)} derived\n")

    bundle = {
        "features": list(F.MODEL_FEATURES),
        "required_input": list(F.REQUIRED_INPUT),
    }

    for inv in (1, 2):
        y = df[f"dg{inv}_state"].to_numpy()
        clf = RandomForestClassifier(n_estimators=N_TREES, random_state=SEED,
                                     n_jobs=-1)
        clf.fit(X, y)
        bundle[f"fault_dg{inv}"] = clf
        print(f"  fault_dg{inv}   fitted, {len(np.unique(y))} classes, "
              f"train acc {clf.score(X, y)*100:.2f} %")

    for tgt in ("R_a", "R_b", "R_c"):
        y = df[tgt].to_numpy()
        reg = RandomForestRegressor(n_estimators=N_TREES, random_state=SEED,
                                    n_jobs=-1)
        reg.fit(X, y)
        bundle[tgt] = reg
        print(f"  {tgt}         fitted, train R2 {reg.score(X, y):.4f}")

    bundle["meta"] = {
        "trained_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": path.name,
        "n_rows": int(len(df)),
        "n_load_settings": int(df.groupby(["R_a", "R_b", "R_c"]).ngroups),
        "n_trees": N_TREES,
        "seed": SEED,
        "sklearn": __import__("sklearn").__version__,
        "git_commit": git_commit(),
        "note": ("Trained on the full dataset. The FAULT head is what ships. "
                 "The R_a/R_b/R_c regressors are kept for comparison only - "
                 "predict.py returns the analytic estimate instead, because a "
                 "forest can only return resistances near ones it has seen. "
                 "Measured on 588 runs at resistances never trained on: "
                 "analytic MAE 0.003 ohm, forest MAE 3.4 ohm, the forest "
                 "snapping to its nearest trained level. Fault head on those "
                 "same unseen conditions: 98.8 % on the 49 combined states."),
    }

    outdir = ROOT / "models"
    outdir.mkdir(exist_ok=True)
    out = outdir / "fault_diagnosis.joblib"
    joblib.dump(bundle, out, compress=3)

    with open(outdir / "manifest.json", "w") as f:
        json.dump({"meta": bundle["meta"],
                   "required_input": bundle["required_input"],
                   "model_features": bundle["features"]}, f, indent=2)

    print(f"\nwrote {out.relative_to(ROOT)}  "
          f"({out.stat().st_size/1024/1024:.1f} MB)")
    print(f"wrote {(outdir / 'manifest.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
