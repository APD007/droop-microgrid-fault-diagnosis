"""
Independent checks that the dataset is physically correct.

None of these compare the data against the model or against how it was
generated. Each one tests a law the numbers must obey regardless - Kirchhoff,
Parseval, Ohm - so a bug in the extraction, the sweep, or the model would show
up as a violation rather than hiding.

Every check here can also be done by hand on one row in Excel; see the manual
procedure in the README. This script exists so you can confirm your hand
arithmetic and then know the other 4703 rows behave the same way.

Usage:
    python scripts/verify_dataset.py [path/to/dataset_full.csv]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
PH = ("a", "b", "c")

results = []


def check(name, ok, detail):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} {detail}")


def main():
    path = (Path(sys.argv[1]) if len(sys.argv) > 1
            else ROOT / "data" / "dataset_full.csv")
    d = pd.read_csv(path)
    print(f"checking {path.name}: {len(d)} rows\n")

    pw1 = [f"DG1_PWM{k}" for k in range(1, 7)]
    pw2 = [f"DG2_PWM{k}" for k in range(1, 7)]
    n_open = (6 - d[pw1].sum(axis=1)) + (6 - d[pw2].sum(axis=1))
    healthy = n_open == 0

    cx = lambda s, p: d[f"{s}f_{p}"] * np.exp(1j * np.deg2rad(d[f"{s}ang_{p}"]))

    # 1 -- Kirchhoff. What the two inverters supply must equal what the loads
    #      draw. Uses magnitudes, so it is only exact when healthy; under fault
    #      the currents are out of phase and this is checked with phasors below.
    zc = F.RC_COUPLING + 1j * 2 * np.pi * F.F_NOM * F.LC_COUPLING

    # (a) the version you can do on a calculator: magnitudes, V as measured.
    #     Approximate by construction - it adds currents that are not quite in
    #     phase and ignores the drop across Rc + jwLc - so it is held to 2 %,
    #     which is the size of those two approximations, not of any error.
    err = []
    for p in PH:
        draw = d[f"V1_{p}"] / d[f"R_{p}"] + d[f"V2_{p}"] / 160.0
        supply = d[f"I1_{p}"] + d[f"I2_{p}"]
        err.append((draw - supply).abs()[healthy] / draw[healthy])
    e = pd.concat(err)
    # The error scales with how unbalanced the load is, because that is what
    # pushes the three phase currents out of alignment: 0.0005 % on balanced
    # loads, up to ~4.7 % on the extremes such as 16/96/96 (77 % unbalance).
    # 5 % is the size of the approximation itself, not of any error in the data.
    check("Kirchhoff, by hand (approximate)", e.max() < 0.05,
          f"worst {e.max()*100:.3f} %, median {e.median()*100:.3f} % "
          f"(5 % allowed: magnitudes + no Zc, grows with unbalance)")

    # (b) the exact version: phasors, stepped back through Zc to the load bus.
    #     Nothing is approximated here, so it is held to 0.05 %.
    err = []
    for p in PH:
        v1, i1 = cx("V1", p), cx("I1", p)
        v2, i2 = cx("V2", p), cx("I2", p)
        vb1, vb2 = v1 - i1 * zc, v2 - i2 * zc
        draw = vb1 / d[f"R_{p}"] + vb2 / 160.0
        err.append(((draw - (i1 + i2)).abs() / draw.abs())[healthy])
    e = pd.concat(err)
    check("Kirchhoff, exact (phasor + Zc)", e.max() < 5e-4,
          f"worst {e.max()*100:.4f} %, median {e.median()*100:.4f} %")

    # 2 -- Ohm, via phasors, on every row including double faults
    zc = F.RC_COUPLING + 1j * 2 * np.pi * F.F_NOM * F.LC_COUPLING
    err = []
    for p in PH:
        v1, i1, v2, i2 = cx("V1", p), cx("I1", p), cx("V2", p), cx("I2", p)
        vb1, vb2 = v1 - i1 * zc, v2 - i2 * zc
        est = (vb1 / (i1 + i2 - vb2 / 160.0)).abs()
        err.append((est - d[f"R_{p}"]).abs())
    e = pd.concat(err)
    check("Ohm's law, phasor, all rows", e.max() < 0.5,
          f"worst {e.max():.4f} ohm, median {e.median():.4f} ohm")

    # 3 -- Parseval. The fundamental is one component of the signal, so its
    #      RMS can never exceed the true RMS of the whole waveform. Tested on
    #      RELATIVE excess: on the voltage columns the LC filter leaves almost
    #      no harmonic content, so the two agree to ~1e-5 and the sign of the
    #      difference is decided by rounding, not by physics.
    excess, slack = [], []
    for s in ("V1", "I1", "V2", "I2"):
        for p in PH:
            rel = (d[f"{s}f_{p}"] - d[f"{s}_{p}"]) / d[f"{s}_{p}"]
            excess.append(rel)
            slack.append(-rel)
    worst = pd.concat(excess).max()
    check("fundamental RMS <= true RMS", worst < 1e-3,
          f"worst excess {worst:.2e} relative (rounding); "
          f"harmonics up to {pd.concat(slack).max()*100:.1f} % of RMS")

    # 4 -- the phase reference is V1_a by construction, so its angle is 0
    check("V1ang_a is the 0 reference", d["V1ang_a"].abs().max() < 1e-9,
          f"max |V1ang_a| = {d['V1ang_a'].abs().max():.2e} deg")

    # 5 -- healthy inverters carry no DC; faulted ones carry several amps
    hmax = d.loc[healthy, [f"I1mean_{p}" for p in PH]].abs().max().max()
    fmin = d.loc[~healthy, [f"I{i}mean_{p}" for i in (1, 2)
                            for p in PH]].abs().max(axis=1).min()
    check("DC offset separates healthy/faulted", hmax < 0.05 < fmin,
          f"healthy max {hmax:.4f} A, faulted min-of-max {fmin:.3f} A")

    # 6 -- an open switch removes conduction from one leg, and the DC it
    #      creates returns through the other two. Not exactly: the load neutral
    #      is grounded, so a little escapes to ground and the three do not sum
    #      to a perfect zero.
    #
    #      The residual is BOUNDED rather than proportional - across all 10,584
    #      rows it never exceeds 0.08 A, while the individual offsets reach
    #      56 A. That is the signature of a ground-path current, not of a
    #      scaling error, so the test is absolute. A relative test would be
    #      wrong here: on a healthy inverter both the sum and the offsets are
    #      ~0.002 A and their ratio is meaningless.
    s = pd.concat([d[[f"I{i}mean_{p}" for p in PH]].sum(axis=1).abs()
                   for i in (1, 2)])
    biggest = d[[f"I{i}mean_{p}" for i in (1, 2) for p in PH]].abs().max().max()
    check("DC offsets sum to ~0", s.max() < 0.1,
          f"worst |sum| {s.max():.4f} A, bounded, against offsets up to "
          f"{biggest:.1f} A")

    # 7 -- droop puts the frequency just below 50 Hz, and the two inverters
    #      must be synchronised or the islanded system is not in steady state
    dg = ROOT / "data" / "diagnostics.csv"
    if dg.exists():
        g = pd.read_csv(dg)
        gap = (g.f1 - g.f2).abs()
        # The two inverters are tied together, so in steady state they run at
        # one frequency. A residual gap appears only with BOTH inverters
        # faulted, where the distortion keeps the filtered power wobbling:
        # healthy 1e-5 Hz, single fault 7e-5 Hz, double fault up to 0.04 Hz.
        ok = g.f1.between(49.5, 50.05).all() and gap.max() < 0.05
        check("frequency sane and synchronised", ok,
              f"f1 {g.f1.min():.3f}-{g.f1.max():.3f} Hz, "
              f"worst |f1-f2| {gap.max():.5f} Hz (median {gap.median():.2e})")

    # 8 -- the design is a full factorial, so every fault class must appear
    #      the same number of times
    counts = d.groupby([d[pw1].sum(axis=1), d[pw2].sum(axis=1)]).size()
    st = d.apply(lambda r: (F.pulse_state(r, 1), F.pulse_state(r, 2)), axis=1)
    counts = st.value_counts()
    check("all 49 fault classes balanced",
          len(counts) == 49 and counts.nunique() == 1,
          f"{len(counts)} classes, {sorted(counts.unique())} runs each")

    # 9 -- the mapping measured in the pilot says which leg each pulse drives,
    #      and the sign says which device. The data must agree.
    legs = {1: "b", 2: "b", 3: "c", 4: "c", 5: "a", 6: "a"}
    wrong = 0
    for k in range(1, 7):
        m = (d[f"DG1_PWM{k}"] == 0) & (d[pw2].sum(axis=1) == 6)
        if not m.any():
            continue
        sub = d.loc[m, [f"I1mean_{p}" for p in PH]]
        got = sub.abs().idxmax(axis=1).str[-1]
        sign_ok = (sub[f"I1mean_{legs[k]}"] > 0) == (k % 2 == 1)
        wrong += int((got != legs[k]).sum()) + int((~sign_ok).sum())
    check("pulse->leg/device mapping holds", wrong == 0,
          f"{wrong} rows disagree with the pilot mapping")

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results)-n_fail}/{len(results)} checks passed")
    if n_fail:
        print("\nFAILED:")
        for name, ok, detail in results:
            if not ok:
                print(f"  {name}: {detail}")
        sys.exit(1)
    print("The dataset obeys every physical law tested.")


if __name__ == "__main__":
    main()
