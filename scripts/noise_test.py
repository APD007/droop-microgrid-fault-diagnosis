"""
How much of the accuracy survives realistic measurement noise?

The dataset is simulation output and therefore noise-free. A real installation
has sensor noise, quantisation and transducer error, so a model validated only
on clean data is not yet evidence of anything practical. This measures the
degradation directly.

Noise model. Each measured quantity gets independent Gaussian error at a
fraction p of its own magnitude:

    magnitudes  x  ->  x + N(0, p*|x|)
    DC offsets  x  ->  x + N(0, p*|I_rms of the same phase|)
                       scaled against the RMS, not against itself, because
                       the DC offset is near zero when healthy and a
                       percentage of zero is not a noise model
    angles      a  ->  a + N(0, degrees(p))
                       a fractional amplitude error of p perturbs the phase
                       by about atan(p) radians

Two scenarios, because they answer different questions:

    train clean, test noisy   what happens if the model meets real data
    train noisy, test noisy   whether training with noise (augmentation)
                              recovers the loss

Usage:
    python scripts/noise_test.py [path/to/dataset_full.csv]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260823
LEVELS = [0.0, 0.001, 0.005, 0.01, 0.02, 0.05]
N_TREES = 200          # fewer than the shipped model; this is a sweep


def add_noise(df, p, rng):
    """Return a copy of df with the 42 measured columns perturbed."""
    if p == 0:
        return df.copy()
    out = df.copy()

    for c in F.MEASURED_RMS + [c for c in F.MEASURED_FUND if "ang" not in c]:
        out[c] = df[c] + rng.normal(0, p * df[c].abs(), len(df))

    for c in F.MEASURED_DC:                      # I1mean_a -> I1_a
        ref = c.replace("mean", "")
        out[c] = df[c] + rng.normal(0, p * df[ref].abs(), len(df))

    sigma_deg = np.degrees(np.arctan(p))
    for c in [c for c in F.MEASURED_FUND if "ang" in c]:
        out[c] = df[c] + rng.normal(0, sigma_deg, len(df))

    return out


def build(df):
    df = df.copy()
    F.derive(df)
    return df[F.MODEL_FEATURES].to_numpy()


def main():
    path = (Path(sys.argv[1]) if len(sys.argv) > 1
            else ROOT / "data" / "dataset_full.csv")
    raw = pd.read_csv(path)
    raw["dg1_state"] = raw.apply(lambda r: F.pulse_state(r, 1), axis=1)
    raw["dg2_state"] = raw.apply(lambda r: F.pulse_state(r, 2), axis=1)
    groups = (raw["R_a"].astype(str) + "_" + raw["R_b"].astype(str)
              + "_" + raw["R_c"].astype(str)).to_numpy()

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25,
                                    random_state=SEED).split(raw, groups=groups))
    print(f"{len(raw)} rows, train {len(tr)} / test {len(te)}, "
          f"whole load settings held out\n")

    y1, y2 = raw["dg1_state"].to_numpy(), raw["dg2_state"].to_numpy()
    rng = np.random.default_rng(SEED)

    X_clean = build(raw)
    print(f"{'noise':>8s}  {'--- train clean, test noisy ---':^34s}   "
          f"{'--- train noisy, test noisy ---':^34s}")
    print(f"{'':>8s}  {'49-state':>9s} {'R_a MAE':>11s} {'R_c MAE':>11s}   "
          f"{'49-state':>9s} {'R_a MAE':>11s} {'R_c MAE':>11s}")

    rows = []
    for p in LEVELS:
        X_noisy = build(add_noise(raw, p, rng))
        line = [f"{p*100:6.1f} %"]
        rec = {"noise_pct": p * 100}

        for label, Xtr in (("clean", X_clean), ("noisy", X_noisy)):
            preds = {}
            for inv, y in ((1, y1), (2, y2)):
                clf = RandomForestClassifier(n_estimators=N_TREES,
                                             random_state=SEED, n_jobs=-1)
                clf.fit(Xtr[tr], y[tr])
                preds[inv] = clf.predict(X_noisy[te])
            both = float(np.mean((preds[1] == y1[te]) & (preds[2] == y2[te])))

            maes = {}
            for tgt in ("R_a", "R_c"):
                yy = raw[tgt].to_numpy()
                reg = RandomForestRegressor(n_estimators=N_TREES,
                                            random_state=SEED, n_jobs=-1)
                reg.fit(Xtr[tr], yy[tr])
                maes[tgt] = mean_absolute_error(yy[te], reg.predict(X_noisy[te]))

            line += [f"{both*100:8.2f} %", f"{maes['R_a']:9.3f} oh",
                     f"{maes['R_c']:9.3f} oh"]
            rec[f"{label}_49state"] = both
            rec[f"{label}_R_a_mae"] = maes["R_a"]
            rec[f"{label}_R_c_mae"] = maes["R_c"]

        rows.append(rec)
        print("  ".join(line))

    out = ROOT / "results" / "noise_robustness.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}")

    base = rows[0]["clean_49state"]
    for r in rows[1:]:
        if r["clean_49state"] < base - 0.05:
            print(f"\nfault accuracy first drops more than 5 points at "
                  f"{r['noise_pct']:.1f} % noise "
                  f"({r['clean_49state']*100:.1f} % vs {base*100:.1f} % clean)")
            break
    else:
        print(f"\nfault accuracy stays within 5 points of clean across every "
              f"level tested, up to {LEVELS[-1]*100:.0f} %")


if __name__ == "__main__":
    main()
