"""
Feature definitions shared by training and inference.

Everything that turns a row of measurements into a model input lives here and
nowhere else. Training and prediction import the same functions, so the two
cannot drift apart - which is the usual way a model that scored well in
testing quietly produces nonsense in use.

Column families
---------------
MEASURED_RMS   12  true RMS of Vabc and Iabc at both buses
MEASURED_DC     6  DC offset of the phase currents
MEASURED_FUND  24  fundamental phasor: 12 magnitudes + 12 angles
                   (angles in degrees, referenced to V1_a)

Those 42 are what a caller must supply. The 9 DERIVED columns below are
computed from them by derive() and must never be supplied by the caller.
"""

import numpy as np

PHASES = ("a", "b", "c")

MEASURED_RMS = [f"{s}_{p}" for s in ("V1", "I1", "V2", "I2") for p in PHASES]
MEASURED_DC = [f"{s}_{p}" for s in ("I1mean", "I2mean") for p in PHASES]
MEASURED_FUND = ([f"{s}f_{p}" for s in ("V1", "I1", "V2", "I2") for p in PHASES]
                 + [f"{s}ang_{p}" for s in ("V1", "I1", "V2", "I2") for p in PHASES])

REQUIRED_INPUT = MEASURED_RMS + MEASURED_DC + MEASURED_FUND      # 42

DERIVED = ([f"Z1_{p}" for p in PHASES] + [f"Z2_{p}" for p in PHASES]
           + [f"Rest_{p}" for p in PHASES])                       # 9

MODEL_FEATURES = REQUIRED_INPUT + DERIVED                         # 51

# --- plant constants used by the derivation ----------------------------
R_BANK_C = 160.0        # bank C, on DG2's bus, never varied
RC_COUPLING = 0.03      # per-inverter coupling resistance, ohm
LC_COUPLING = 0.35e-3   # per-inverter coupling inductance, H
F_NOM = 50.0            # droop shifts f by ~0.03 %, negligible inside Zc

_EPS = 1e-12


def derive(df):
    """Add the 9 physics-derived columns. Returns the same frame, modified.

    Rest_a/b/c is an analytic estimate of the bank A resistance. Three things
    make it correct, and dropping any one of them breaks it:

      phasors, not magnitudes - bank A is fed by BOTH inverters, so two
        currents must be summed, and under fault they are not in phase

      fundamental, not true RMS - the load is a pure resistor and therefore
        linear, so I = V/R holds exactly at the fundamental however distorted
        the total waveform is; true RMS mixes in harmonics that do not obey it

      step back through the coupling impedance - V1 and V2 are measured at
        each filter-capacitor bus, but the load banks hang off the buses on
        the far side of Rc + jwLc. Correcting for that drop improves median
        accuracy from 0.039 ohm to 0.0011 ohm, a factor of 35.
    """
    zc = RC_COUPLING + 1j * 2 * np.pi * F_NOM * LC_COUPLING

    for p in PHASES:
        df[f"Z1_{p}"] = df[f"V1_{p}"] / (df[f"I1_{p}"] + _EPS)
        df[f"Z2_{p}"] = df[f"V2_{p}"] / (df[f"I2_{p}"] + _EPS)

        def cx(sig, ph=p):
            return (df[f"{sig}f_{ph}"]
                    * np.exp(1j * np.deg2rad(df[f"{sig}ang_{ph}"])))

        v1, i1, v2, i2 = cx("V1"), cx("I1"), cx("V2"), cx("I2")
        vbus1, vbus2 = v1 - i1 * zc, v2 - i2 * zc
        i_bank_a = i1 + i2 - vbus2 / R_BANK_C
        df[f"Rest_{p}"] = (vbus1 / (i_bank_a + _EPS)).abs()

    df[DERIVED] = (df[DERIVED].replace([np.inf, -np.inf], np.nan)
                              .clip(-1e4, 1e4).fillna(0.0))
    return df


def pulse_state(row, inverter):
    """0 = healthy, k = pulse k open. Assumes at most one pulse open."""
    zeros = [k for k in range(1, 7) if row[f"DG{inverter}_PWM{k}"] == 0]
    return zeros[0] if zeros else 0


def flags_from_state(state):
    """Inverse of pulse_state: a 7-class label back to six 1/0 flags."""
    flags = [1] * 6
    if state:
        flags[int(state) - 1] = 0
    return flags


def unbalance_pct(r):
    """NEMA-style degree of unbalance: max deviation from mean, percent.

    r is a frame with three resistance columns.
    """
    m = r.mean(axis=1)
    return 100.0 * (r.sub(m, axis=0).abs().max(axis=1) / m)


def check_input(df):
    """Raise with a useful message if the caller's frame is unusable."""
    missing = [c for c in REQUIRED_INPUT if c not in df.columns]
    if missing:
        raise ValueError(
            f"{len(missing)} required column(s) missing, first few: "
            f"{missing[:8]}\n"
            f"Input must carry all {len(REQUIRED_INPUT)} measured columns: "
            f"{len(MEASURED_RMS)} true RMS, {len(MEASURED_DC)} DC offset, "
            f"{len(MEASURED_FUND)} fundamental phasor.")

    bad = df[REQUIRED_INPUT].isna().any(axis=1)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} row(s) contain NaN in the measured "
                         f"columns; first at index {int(bad.idxmax())}")

    v = df[[f"V1_{p}" for p in PHASES] + [f"V2_{p}" for p in PHASES]]
    if not ((v.abs() > 1).all().all() and (v.abs() < 1000).all().all()):
        raise ValueError("voltage columns outside 1..1000 V - check units and "
                         "that RMS (not peak) values were supplied")
    return df
