"""
Report figures.

Four, each answering one question:

  confusion_dg1.png       where does the fault head actually go wrong?
  feature_importance.png  which columns are doing the work?
  accuracy_by_features.png  what do the extra columns buy?
  noise_robustness.png    how much survives measurement noise?

Light mode only, deliberately - these are print figures for a report, not a
web page. Palette is the validated blue / orange / aqua / violet categorical
set (passes CVD separation, normal-vision floor and lightness band on
all-pairs) with the single-hue blue ramp for the sequential heatmap.

Usage:
    python scripts/make_figures.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "figures"
SEED = 20260823

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8984"
GRID = "#e5e4e0"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]      # validated set
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq", BLUES)

# measured mapping, from the pilot: pulse -> leg and device
PULSE_LABEL = {0: "healthy", 1: "p1\nb lo", 2: "p2\nb up", 3: "p3\nc lo",
               4: "p4\nc up", 5: "p5\na lo", 6: "p6\na up"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "xtick.color": INK_3, "ytick.color": INK_3,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "axes.grid": False,
})


def frame(ax, keep=("left", "bottom")):
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(s in keep)
    ax.tick_params(length=3, width=0.8)


def load():
    df = pd.read_csv(ROOT / "data" / "dataset_full.csv")
    F.derive(df)
    df["dg1_state"] = df.apply(lambda r: F.pulse_state(r, 1), axis=1)
    df["dg2_state"] = df.apply(lambda r: F.pulse_state(r, 2), axis=1)
    groups = (df["R_a"].astype(str) + "_" + df["R_b"].astype(str)
              + "_" + df["R_c"].astype(str)).to_numpy()
    return df, groups


def fig_confusion(df, groups):
    X = df[F.MODEL_FEATURES].to_numpy()
    y = df["dg1_state"].to_numpy()
    tr, te = next(GroupShuffleSplit(1, test_size=.25, random_state=SEED)
                  .split(X, groups=groups))
    clf = RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1)
    clf.fit(X[tr], y[tr])
    cm = confusion_matrix(y[te], clf.predict(X[te]), labels=range(7))
    acc = np.trace(cm) / cm.sum()

    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    norm = cm / cm.sum(axis=1, keepdims=True)
    ax.imshow(norm, cmap=SEQ, vmin=0, vmax=1)

    for i in range(7):
        for j in range(7):
            if cm[i, j] == 0:
                continue
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if norm[i, j] > .55 else INK_2,
                    fontweight="600" if i == j else "normal")

    ax.set_xticks(range(7), [PULSE_LABEL[k] for k in range(7)], fontsize=7.5)
    ax.set_yticks(range(7), [PULSE_LABEL[k].replace("\n", " ") for k in range(7)],
                  fontsize=7.5)
    ax.set_xlabel("predicted", color=INK_2)
    ax.set_ylabel("actual", color=INK_2)
    ax.set_title(f"Inverter 1 fault state  ·  {acc*100:.1f}% correct",
                 fontsize=11, pad=12, loc="left")
    ax.text(0, -1.15, "held-out load settings only · counts shown, shading is row-normalised",
            fontsize=7.5, color=INK_3, transform=ax.get_yaxis_transform(),
            ha="left", clip_on=False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(OUT / "confusion_dg1.png", dpi=200)
    plt.close(fig)
    return acc


def family(col):
    if col.startswith(("Z1", "Z2", "Rest")):
        return "derived"
    if "ang" in col:
        return "fundamental angle"
    if "f_" in col:
        return "fundamental magnitude"
    if "mean" in col:
        return "DC offset"
    return "true RMS"


FAM_ORDER = ["true RMS", "DC offset", "fundamental magnitude",
             "fundamental angle", "derived"]
FAM_COLOR = {"true RMS": CAT[0], "DC offset": CAT[1],
             "fundamental magnitude": CAT[2], "fundamental angle": CAT[2],
             "derived": CAT[3]}


def fig_importance(df, groups):
    X = df[F.MODEL_FEATURES].to_numpy()
    y = df["dg1_state"].to_numpy()
    clf = RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1)
    clf.fit(X, y)
    imp = pd.Series(clf.feature_importances_, index=F.MODEL_FEATURES)
    top = imp.sort_values(ascending=True).tail(18)

    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    fams = [family(c) for c in top.index]
    ax.barh(range(len(top)), top.values, height=.62,
            color=[FAM_COLOR[f] for f in fams])
    ax.set_yticks(range(len(top)), top.index, fontsize=8)
    ax.set_xlabel("importance", color=INK_2)
    ax.set_title("What the fault head actually uses", fontsize=11, pad=10,
                 loc="left")
    ax.xaxis.grid(True, color=GRID, lw=.7)
    ax.set_axisbelow(True)
    frame(ax, keep=("bottom",))

    seen, handles = [], []
    for f in FAM_ORDER:
        if f in fams and FAM_COLOR[f] not in seen:
            seen.append(FAM_COLOR[f])
            handles.append(plt.Rectangle((0, 0), 1, 1, color=FAM_COLOR[f],
                                         label=f))
    leg = ax.legend(handles=handles, frameon=False, fontsize=8,
                    loc="lower right", labelcolor=INK_2)
    for t in leg.get_texts():
        t.set_color(INK_2)
    fig.tight_layout()
    fig.savefig(OUT / "feature_importance.png", dpi=200)
    plt.close(fig)


def fig_featuresets():
    sets = ["12 true RMS\nonly", "+ 6 DC\noffsets", "+ 24 fundamental\nphasors"]
    vals = [46.43, 91.50, 94.90]
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    bars = ax.bar(sets, vals, width=.55, color=[CAT[0], CAT[0], CAT[0]])
    bars[2].set_color(CAT[2])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.6, f"{v:.1f}%",
                ha="center", fontsize=10, color=INK, fontweight="600")
    ax.set_ylim(0, 108)
    ax.set_ylabel("accuracy, 49 combined states", color=INK_2)
    ax.set_title("What the extra columns buy", fontsize=11, pad=10, loc="left")
    ax.yaxis.grid(True, color=GRID, lw=.7)
    ax.set_axisbelow(True)
    frame(ax, keep=("bottom",))
    fig.tight_layout()
    fig.savefig(OUT / "accuracy_by_features.png", dpi=200)
    plt.close(fig)


def fig_noise():
    src = ROOT / "results" / "noise_robustness.csv"
    if not src.exists():
        print("  (skipping noise figure - run scripts/noise_test.py first)")
        return
    d = pd.read_csv(src)
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    ax.plot(d.noise_pct, d.clean_49state * 100, lw=2, color=CAT[0],
            marker="o", ms=5, label="trained on clean data")
    ax.plot(d.noise_pct, d.noisy_49state * 100, lw=2, color=CAT[1],
            marker="s", ms=5, label="trained with noise")
    for _, r in d.tail(1).iterrows():
        ax.annotate(f"{r.clean_49state*100:.0f}%", (r.noise_pct, r.clean_49state*100),
                    textcoords="offset points", xytext=(6, -2), fontsize=8.5,
                    color=INK_2)
        ax.annotate(f"{r.noisy_49state*100:.0f}%", (r.noise_pct, r.noisy_49state*100),
                    textcoords="offset points", xytext=(6, -2), fontsize=8.5,
                    color=INK_2)
    ax.set_xlabel("measurement noise, % of reading", color=INK_2)
    ax.set_ylabel("accuracy, 49 states", color=INK_2)
    ax.set_title("Accuracy against measurement noise", fontsize=11, pad=10,
                 loc="left")
    ax.yaxis.grid(True, color=GRID, lw=.7)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 105)
    leg = ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    for t in leg.get_texts():
        t.set_color(INK_2)
    frame(ax, keep=("bottom", "left"))
    fig.tight_layout()
    fig.savefig(OUT / "noise_robustness.png", dpi=200)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df, groups = load()
    print("building figures:")
    acc = fig_confusion(df, groups);  print(f"  confusion_dg1.png        ({acc*100:.1f}%)")
    fig_importance(df, groups);       print("  feature_importance.png")
    fig_featuresets();                print("  accuracy_by_features.png")
    fig_noise();                      print("  noise_robustness.png")
    print(f"\nwrote to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
