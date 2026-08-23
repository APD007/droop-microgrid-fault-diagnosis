"""
Run the trained fault-diagnosis model on new data.

This is the handover script. Give it a CSV of measurements, get back the
fault state and the load resistances.

    python scripts/predict.py <input.csv> [-o output.csv]

INPUT must contain these 42 columns, in any order:

    V1_a V1_b V1_c I1_a I1_b I1_c V2_a V2_b V2_c I2_a I2_b I2_c
        true RMS over a whole number of fundamental cycles

    I1mean_a I1mean_b I1mean_c I2mean_a I2mean_b I2mean_c
        mean (DC offset) of each phase current over the same window

    V1f_* I1f_* V2f_* I2f_*        fundamental magnitude, RMS-scaled
    V1ang_* I1ang_* V2ang_* I2ang_*  fundamental angle, degrees, ref V1_a

Any other columns are carried through to the output untouched, so a file that
already has the true answers in it can be passed straight in and the
predictions will sit alongside them for comparison.

To produce that file from a Simulink run, use scripts/features_from_logs.m.

OUTPUT adds:
    DG1_PWM1..6, DG2_PWM1..6   predicted, 1 = healthy, 0 = open switch
    R_a_pred R_b_pred R_c_pred predicted resistances, ohm
    unbalance_pred             degree of unbalance, percent
    DG1_state DG2_state        0 = healthy, k = pulse k open
    DG1_conf DG2_conf          model confidence, 0..1
"""

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "fault_diagnosis.joblib"


def main():
    ap = argparse.ArgumentParser(description="Predict fault state and load "
                                             "resistances from measurements.")
    ap.add_argument("input", help="CSV of measurements")
    ap.add_argument("-o", "--output", help="where to write (default: "
                                           "<input>_predictions.csv)")
    ap.add_argument("-m", "--model", default=str(MODEL))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        sys.exit(f"no model at {model_path}\nrun: python scripts/train_final.py")

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"no such file: {src}")

    bundle = joblib.load(model_path)
    df = pd.read_csv(src)

    # fail loudly and specifically rather than predicting from bad input.
    # A traceback is the wrong output for a handover script - say what is
    # wrong with the file and stop.
    try:
        F.check_input(df)
        F.derive(df)
    except ValueError as e:
        sys.exit(f"\ncannot use {src.name}:\n\n  {e}\n\n"
                 f"See scripts/features_from_logs.m to produce these columns "
                 f"from a Simulink run.")

    missing = [c for c in bundle["features"] if c not in df.columns]
    if missing:
        sys.exit(f"model expects columns this input cannot provide: {missing[:8]}")

    X = df[bundle["features"]].to_numpy()

    out = df.copy()
    for inv in (1, 2):
        clf = bundle[f"fault_dg{inv}"]
        state = clf.predict(X)
        conf = clf.predict_proba(X).max(axis=1)
        out[f"DG{inv}_state"] = state
        out[f"DG{inv}_conf"] = np.round(conf, 4)
        flags = np.array([F.flags_from_state(s) for s in state])
        for k in range(6):
            out[f"DG{inv}_PWM{k+1}_pred"] = flags[:, k]

    # ---- resistances: analytic, NOT the random forest ---------------------
    # A forest predicts by averaging training leaf values, so it can only ever
    # return resistances near ones it has seen. Measured on a run at a true
    # 40 / 40 / 72 ohm, the forest returns 36.1 / 43.0 / 64.0 - snapping to its
    # training lattice - while the analytic estimate returns 40.0 / 40.0 / 72.0.
    # The forest predictions are kept alongside as *_rf for comparison, but the
    # analytic value is the answer: it is exact, it works at any resistance,
    # and it can be checked by hand.
    for p in ("a", "b", "c"):
        out[f"R_{p}_pred"] = np.round(df[f"Rest_{p}"], 3)
        out[f"R_{p}_pred_rf"] = np.round(bundle[f"R_{p}"].predict(X), 3)

    # derived from the predicted resistances rather than fitted separately -
    # a tree cannot represent max|R-mean|/mean anyway
    P = out[["R_a_pred", "R_b_pred", "R_c_pred"]]
    out["unbalance_pred"] = np.round(F.unbalance_pct(P), 3)

    dst = Path(args.output) if args.output else src.with_name(
        src.stem + "_predictions.csv")
    out.to_csv(dst, index=False)

    if not args.quiet:
        print(f"model    : {model_path.name}  "
              f"(trained {bundle['meta']['trained_utc']}, "
              f"commit {bundle['meta']['git_commit']})")
        print(f"input    : {src.name}  ({len(df)} rows)")
        print(f"output   : {dst}")

        low = (out[["DG1_conf", "DG2_conf"]].min(axis=1) < 0.5).sum()
        if low:
            print(f"\n  note: {low} row(s) predicted with confidence below "
                  f"0.5 - inspect those before trusting them")

        # if the caller supplied ground truth, score it
        if all(c in df.columns for c in ("R_a", "R_b", "R_c")):
            print("\n  ground truth present, scoring:")
            print(f"    {'':6s} {'analytic MAE':>15s} {'forest MAE':>14s}")
            for tgt in ("R_a", "R_b", "R_c"):
                ea = (out[f"{tgt}_pred"] - out[tgt]).abs()
                ef = (out[f"{tgt}_pred_rf"] - out[tgt]).abs()
                print(f"    {tgt:6s} {ea.mean():12.4f} ohm {ef.mean():11.4f} ohm")
        if all(f"DG1_PWM{k}" in df.columns for k in range(1, 7)):
            t1 = df.apply(lambda r: F.pulse_state(r, 1), axis=1)
            t2 = df.apply(lambda r: F.pulse_state(r, 2), axis=1)
            a1 = (out["DG1_state"] == t1).mean()
            a2 = (out["DG2_state"] == t2).mean()
            both = ((out["DG1_state"] == t1) & (out["DG2_state"] == t2)).mean()
            print(f"    inverter 1 {a1*100:6.2f} %    inverter 2 {a2*100:6.2f} %"
                  f"    both {both*100:6.2f} %")


if __name__ == "__main__":
    main()
