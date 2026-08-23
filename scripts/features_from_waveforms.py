"""
Waveforms in a spreadsheet -> the 42 columns predict.py needs.

Use this when the test data arrives as sampled waveforms rather than as a
Simulink SimulationOutput. It is a Python port of extract_features.m, so no
MATLAB is required at the receiving end.

INPUT: a .xlsx or .csv table of time series, one row per sample, with columns

    time        seconds
    V1_a V1_b V1_c    inverter 1 terminal voltages, volts, instantaneous
    I1_a I1_b I1_c    inverter 1 output currents, amps, instantaneous
    V2_a V2_b V2_c    inverter 2
    I2_a I2_b I2_c    inverter 2
    f1          OPTIONAL droop frequency, Hz. If absent it is estimated from
                the V1_a waveform, which is accurate to a few mHz and quite
                good enough for sizing the averaging window.

One file = one operating condition = one output row. For several conditions,
either add a 'run' or 'case' column to separate them, or pass several files.

    python scripts/features_from_waveforms.py waves.xlsx -o features.csv
    python scripts/predict.py features.csv

The sampling rate must resolve the switching ripple - at least ~20 kHz for a
10 kHz carrier. Anything slower has already lost the harmonic content the
fault head reads, and the DC-offset feature in particular.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

NCYC = 4              # must match training; the window is part of the features
SIGNALS = ("V1", "I1", "V2", "I2")


def read_table(path):
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(p)
    return pd.read_csv(p)


def estimate_f(t, x, lo=45.0, hi=55.0):
    """Fundamental frequency from one waveform, by interpolated FFT peak.

    Used only when the caller does not supply f1. Droop puts the true value
    near 49.98 Hz, so the search is deliberately narrow.
    """
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    dt = float(np.median(np.diff(t)))
    w = np.hanning(n)
    spec = np.abs(np.fft.rfft(x * w))
    freq = np.fft.rfftfreq(n, dt)

    band = (freq >= lo) & (freq <= hi)
    if not band.any():
        raise ValueError(f"no spectral content between {lo} and {hi} Hz - "
                         f"check the time column units (expected seconds)")
    k = np.where(band)[0][np.argmax(spec[band])]

    # parabolic interpolation on the log magnitude sharpens the bin estimate
    if 0 < k < len(spec) - 1:
        a, b, c = np.log(spec[k-1:k+2] + 1e-30)
        k = k + 0.5 * (a - c) / (a - 2*b + c)
    return float(k * (freq[1] - freq[0]))


def phasor(d, t, f):
    """Complex fundamental phasor per column, scaled to RMS magnitude."""
    w = 2 * np.pi * f
    a = 2 * np.mean(d * np.cos(w * t)[:, None], axis=0)
    b = 2 * np.mean(d * np.sin(w * t)[:, None], axis=0)
    return (a - 1j * b) / np.sqrt(2)


def one_run(df):
    """Reduce one operating condition's waveforms to a dict of 42 features."""
    need = ["time"] + [f"{s}_{p}" for s in SIGNALS for p in F.PHASES]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"waveform table is missing: {missing}")

    t = df["time"].to_numpy(float)
    if not np.all(np.diff(t) > 0):
        raise ValueError("time column must be strictly increasing")

    f = (float(df["f1"].iloc[-max(1, len(df)//10):].mean())
         if "f1" in df.columns else estimate_f(t, df["V1_a"].to_numpy()))

    span = t[-1] - t[0]
    if span < NCYC / f:
        raise ValueError(f"record is {span*1000:.1f} ms, need at least "
                         f"{NCYC/f*1000:.1f} ms ({NCYC} cycles at {f:.2f} Hz)")

    sel = t >= t[-1] - NCYC / f          # last whole number of cycles
    tw = t[sel]

    out = {}
    data = {s: df[[f"{s}_{p}" for p in F.PHASES]].to_numpy(float)[sel]
            for s in SIGNALS}

    for s in SIGNALS:                                    # true RMS
        rms = np.sqrt(np.mean(data[s] ** 2, axis=0))
        for i, p in enumerate(F.PHASES):
            out[f"{s}_{p}"] = rms[i]

    for s in ("I1", "I2"):                               # DC offset
        mean = np.mean(data[s], axis=0)
        for i, p in enumerate(F.PHASES):
            out[f"{s}mean_{p}"] = mean[i]

    ph = {s: phasor(data[s], tw, f) for s in SIGNALS}
    ref = np.angle(ph["V1"][0])                          # V1_a is the reference
    for s in SIGNALS:
        mag = np.abs(ph[s])
        ang = (np.degrees(np.angle(ph[s]) - ref) + 180) % 360 - 180
        for i, p in enumerate(F.PHASES):
            out[f"{s}f_{p}"] = mag[i]
            out[f"{s}ang_{p}"] = ang[i]

    out["f1"] = f
    out["n_samples"] = int(sel.sum())
    out["sample_rate_khz"] = round(1 / np.median(np.diff(t)) / 1000, 2)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Waveform tables -> the feature columns predict.py needs.")
    ap.add_argument("inputs", nargs="+", help=".xlsx or .csv waveform tables")
    ap.add_argument("-o", "--output", default="features.csv")
    args = ap.parse_args()

    rows, labels = [], []
    for path in args.inputs:
        df = read_table(path)
        key = next((c for c in ("run", "case", "run_id") if c in df.columns),
                   None)
        groups = ([(v, df[df[key] == v]) for v in df[key].unique()] if key
                  else [(Path(path).stem, df)])
        for label, g in groups:
            try:
                rows.append(one_run(g))
                labels.append(label)
            except ValueError as e:
                sys.exit(f"\n{Path(path).name} [{label}]: {e}\n")

    out = pd.DataFrame(rows)
    out.insert(0, "source", labels)

    rate = out["sample_rate_khz"].min()
    if rate < 20:
        print(f"  WARNING: lowest sample rate is {rate:.1f} kHz. The carrier is "
              f"10 kHz, so below ~20 kHz the harmonic content the fault head "
              f"relies on is already lost. Predictions will be unreliable.")

    out.to_csv(args.output, index=False)
    print(f"wrote {args.output}  ({len(out)} run(s) x {out.shape[1]} columns)")
    print(f"  fundamental: {out.f1.min():.3f} - {out.f1.max():.3f} Hz")
    print(f"  window     : {out.n_samples.min()} - {out.n_samples.max()} samples "
          f"({NCYC} cycles)")
    print(f"\nnow run:  python scripts/predict.py {args.output}")


if __name__ == "__main__":
    main()
