"""
Fault-diagnosis model.

Task, as fixed by the guide's note:

    INPUT   Vabc and Iabc measured at both buses  (12 RMS values)
    OUTPUT  which PWM pulse is open, and the per-phase load resistances

Two heads are trained on the same features:

  1. FAULT HEAD  - which pulse is open.
     Formulated as two 7-class problems (one per inverter: healthy, or one of
     pulses 1-6) rather than twelve independent binary flags. The guide's rule
     is that at most one pulse is open per inverter, and a 7-class formulation
     encodes that constraint structurally - it is incapable of predicting two
     open pulses on one inverter, which twelve independent flags would happily
     do. The twelve 1/0 flags in the guide's sketch are reconstructed from the
     predicted class for reporting.

  2. LOAD HEAD   - R_a, R_b, R_c, plus the degree of unbalance derived from
     them (NEMA-style: max deviation from the mean, as a percentage).

THE SPLIT MATTERS MORE THAN THE MODEL. Every load setting appears 49 times in
the dataset, once per PWM state. A random row split would put 49 near-identical
siblings of every test row into the training set and report accuracy that is
almost pure leakage. Rows are therefore grouped by load setting and whole
groups are held out, so the test set contains load conditions never seen in
training.

Usage:
    python scripts/train_model.py [path/to/dataset.csv]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             mean_absolute_error, r2_score)
from sklearn.model_selection import GroupShuffleSplit, cross_val_predict

ROOT = Path(__file__).resolve().parent.parent

# the guide's stated inputs: Vabc and Iabc at both buses
FEATURES_RMS = ["V1_a", "V1_b", "V1_c", "I1_a", "I1_b", "I1_c",
                "V2_a", "V2_b", "V2_c", "I2_a", "I2_b", "I2_c"]

# the six DC-offset features that separate upper from lower switch faults
FEATURES_DC = ["I1mean_a", "I1mean_b", "I1mean_c",
               "I2mean_a", "I2mean_b", "I2mean_c"]

# Physics-derived features. These are NOT new measurements - every one is
# computed from the twelve the guide specified. They exist because a random
# forest is piecewise-constant: it cannot represent a ratio, and Ohm's law is
# a ratio. Handing it V/I directly does the division the tree cannot.
FEATURES_PHYS = ["Z1_a", "Z1_b", "Z1_c", "Z2_a", "Z2_b", "Z2_c",
                 "Rest_a", "Rest_b", "Rest_c"]

R_BANK_C = 160.0        # bank C sits on DG2's bus and is never varied

TEST_FRACTION = 0.25
SEED = 20260823


# --------------------------------------------------------------- targets
def pulse_state(row, inverter):
    """0 = healthy, k = pulse k open. Relies on at most one being zero."""
    flags = [row[f"DG{inverter}_PWM{k}"] for k in range(1, 7)]
    zeros = [k for k, v in enumerate(flags, start=1) if v == 0]
    return zeros[0] if zeros else 0


def unbalance_pct(r):
    """NEMA-style degree of unbalance: max deviation from mean, percent."""
    m = r.mean(axis=1)
    return 100.0 * (r.sub(m, axis=0).abs().max(axis=1) / m)


def prepare(df):
    df = df.copy()
    df["dg1_state"] = df.apply(lambda r: pulse_state(r, 1), axis=1)
    df["dg2_state"] = df.apply(lambda r: pulse_state(r, 2), axis=1)
    df["unbalance"] = unbalance_pct(df[["R_a", "R_b", "R_c"]])

    # Physics-derived features, per phase.
    #   Z = apparent impedance each inverter sees at its own terminals.
    #   Rest = an estimate of the bank A resistance we are actually trying to
    #          recover. Bank A hangs off DG1's bus and is fed by BOTH inverters:
    #          DG2 supplies its own bank C (fixed 160 ohm) and sends the rest up
    #          the line. So bank A's current is I1 + (I2 - V2/160), and
    #          R_a = V1 / that. This is exact for the healthy balanced case and
    #          approximate otherwise, because RMS magnitudes are being added as
    #          if in phase - good enough to hand a tree the right quantity.
    eps = 1e-9
    for ph in ("a", "b", "c"):
        df[f"Z1_{ph}"] = df[f"V1_{ph}"] / (df[f"I1_{ph}"] + eps)
        df[f"Z2_{ph}"] = df[f"V2_{ph}"] / (df[f"I2_{ph}"] + eps)
        i_bankA = (df[f"I1_{ph}"] + df[f"I2_{ph}"]
                   - df[f"V2_{ph}"] / R_BANK_C)
        df[f"Rest_{ph}"] = df[f"V1_{ph}"] / (i_bankA + eps)
    df[FEATURES_PHYS] = df[FEATURES_PHYS].replace([np.inf, -np.inf], np.nan)
    df[FEATURES_PHYS] = df[FEATURES_PHYS].clip(-1e4, 1e4).fillna(0.0)
    # one group per load setting - the unit that gets held out
    df["load_group"] = (df["R_a"].astype(str) + "_"
                        + df["R_b"].astype(str) + "_"
                        + df["R_c"].astype(str))
    return df


# ----------------------------------------------------------------- eval
def evaluate(df, features, label, cascade=False):
    X = df[features].to_numpy()
    groups = df["load_group"].to_numpy()

    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_FRACTION,
                                 random_state=SEED)
    tr, te = next(splitter.split(X, groups=groups))

    n_tr_groups = df.iloc[tr]["load_group"].nunique()
    n_te_groups = df.iloc[te]["load_group"].nunique()

    print(f"\n{'='*66}")
    print(f"  {label}   ({len(features)} features)")
    print(f"{'='*66}")
    print(f"  train {len(tr):5d} rows / {n_tr_groups:3d} load settings")
    print(f"  test  {len(te):5d} rows / {n_te_groups:3d} load settings  "
          f"(none seen in training)")

    out = {"features": features, "n_train": len(tr), "n_test": len(te)}

    # ---- fault head -----------------------------------------------------
    print("\n  FAULT HEAD - which pulse is open")
    per_inv = {}
    preds = {}
    preds_tr = {}
    for inv in (1, 2):
        y = df[f"dg{inv}_state"].to_numpy()
        clf = RandomForestClassifier(n_estimators=300, random_state=SEED,
                                     n_jobs=-1)
        clf.fit(X[tr], y[tr])
        p = clf.predict(X[te])
        preds[inv] = p
        acc = accuracy_score(y[te], p)
        per_inv[inv] = acc
        print(f"    inverter {inv}: {acc*100:6.2f} %  (7 classes)")
        if cascade:
            # out-of-fold predictions for the training rows. Using in-sample
            # predictions here would hand the load head a near-perfect fault
            # label it will not have at inference time.
            preds_tr[inv] = cross_val_predict(
                RandomForestClassifier(n_estimators=300, random_state=SEED,
                                       n_jobs=-1),
                X[tr], y[tr], cv=5)

    both = np.mean((preds[1] == df["dg1_state"].to_numpy()[te])
                   & (preds[2] == df["dg2_state"].to_numpy()[te]))
    print(f"    both correct: {both*100:6.2f} %  (49 combined states)")
    out["fault"] = {"dg1": per_inv[1], "dg2": per_inv[2], "both": both}

    # where does it go wrong? group errors by leg to expose upper/lower confusion
    y1 = df["dg1_state"].to_numpy()[te]
    cm = confusion_matrix(y1, preds[1], labels=list(range(7)))
    leg_pairs = [(1, 2), (3, 4), (5, 6)]     # measured mapping: same leg
    same_leg = sum(cm[a][b] + cm[b][a] for a, b in leg_pairs)
    total_err = cm.sum() - np.trace(cm)
    if total_err:
        print(f"    of {total_err} inverter-1 errors, {same_leg} "
              f"({same_leg/total_err*100:.0f} %) are upper/lower on the SAME leg")
    out["fault"]["same_leg_error_share"] = (
        float(same_leg / total_err) if total_err else 0.0)

    # ---- load head ------------------------------------------------------
    # In cascade mode the predicted fault state is appended to the features,
    # which is the architecture in the guide's sketch. The rationale: a low
    # current can mean a high resistance OR an open switch, and the load head
    # cannot tell those apart on its own. Telling it the fault state first
    # removes that ambiguity.
    if cascade:
        eye = np.eye(7)
        Xtr = np.hstack([X[tr], eye[preds_tr[1]], eye[preds_tr[2]]])
        Xte = np.hstack([X[te], eye[preds[1]], eye[preds[2]]])
        print("\n  LOAD HEAD - per-phase resistance  "
              "(+ predicted fault state, cascade)")
    else:
        Xtr, Xte = X[tr], X[te]
        print("\n  LOAD HEAD - per-phase resistance")

    load_metrics = {}
    for tgt in ("R_a", "R_b", "R_c", "unbalance"):
        y = df[tgt].to_numpy()
        reg = RandomForestRegressor(n_estimators=300, random_state=SEED,
                                    n_jobs=-1)
        reg.fit(Xtr, y[tr])
        p = reg.predict(Xte)
        mae, r2 = mean_absolute_error(y[te], p), r2_score(y[te], p)
        unit = "%" if tgt == "unbalance" else "ohm"
        print(f"    {tgt:10s} MAE {mae:7.3f} {unit:4s}   R2 {r2:6.3f}")
        load_metrics[tgt] = {"mae": mae, "r2": r2}
    out["load"] = load_metrics

    return out


# ----------------------------------------------------------------- main
def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "dataset_extended.csv"
    if not path.exists():
        sys.exit(f"no dataset at {path}\n"
                 f"run the sweep, then scripts/merge_results.py")

    df = pd.read_csv(path)
    df = prepare(df)

    print(f"dataset: {path.name}")
    print(f"  {len(df)} rows, {df['load_group'].nunique()} load settings, "
          f"{df.groupby(['dg1_state','dg2_state']).ngroups} fault classes present")

    results = {}
    results["rms_only"] = evaluate(df, FEATURES_RMS, "RMS ONLY - the 28-column schema")

    have_dc = all(c in df.columns for c in FEATURES_DC)
    if have_dc:
        results["rms_plus_dc"] = evaluate(
            df, FEATURES_RMS + FEATURES_DC, "RMS + DC OFFSET - the 34-column schema")

        results["cascade"] = evaluate(
            df, FEATURES_RMS + FEATURES_DC,
            "CASCADE - fault state fed into the load head", cascade=True)

        results["physics"] = evaluate(
            df, FEATURES_RMS + FEATURES_DC + FEATURES_PHYS,
            "RMS + DC + PHYSICS-DERIVED (V/I ratios, bank A estimate)")

        print(f"\n{'='*66}")
        print("  DOES THE CASCADE HELP THE LOAD HEAD?")
        print(f"{'='*66}")
        print(f"  {'target':12s} {'direct R2':>12s} {'cascade R2':>12s} {'gain':>8s}")
        for tgt in ("R_a", "R_b", "R_c", "unbalance"):
            d = results["rms_plus_dc"]["load"][tgt]["r2"]
            c = results["cascade"]["load"][tgt]["r2"]
            print(f"  {tgt:12s} {d:12.3f} {c:12.3f} {c-d:+8.3f}")

        a = results["rms_only"]["fault"]["both"]
        b = results["rms_plus_dc"]["fault"]["both"]
        print(f"\n{'='*66}")
        print("  VERDICT on the six extra columns")
        print(f"{'='*66}")
        print(f"  49-state accuracy, RMS only     : {a*100:6.2f} %")
        print(f"  49-state accuracy, RMS + DC     : {b*100:6.2f} %")
        print(f"  difference                      : {(b-a)*100:+6.2f} points")
    else:
        print("\n  (DC-offset columns absent - run on dataset_extended.csv "
              "to compare)")

    outdir = ROOT / "results"
    outdir.mkdir(exist_ok=True)
    with open(outdir / "metrics.json", "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nwrote results/metrics.json")


if __name__ == "__main__":
    main()
