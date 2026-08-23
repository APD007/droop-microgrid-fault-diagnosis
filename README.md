# Droop-controlled microgrid — fault diagnosis

B.Tech final-year project, electrical engineering.

Two parallel droop-controlled inverters in an islanded microgrid, simulated in
Simulink. The project has two stages:

1. **Dataset generation** — sweep the model over every permitted permutation of
   load unbalance and open-switch (IGBT) fault, and reduce each run to a row of
   RMS measurements. 4704 runs.
2. **Fault diagnosis model** — train a model to recover the fault state (which
   pulse is open, on which inverter) and the per-phase load resistances from
   the measured voltages and currents alone.

Stage 1 is what this repository currently contains. Stage 2 begins once the
dataset is complete and validated.

## Layout

```
.
├── setup_paths.m           run this first in MATLAB, once per session
├── requirements.txt        pinned Python dependencies
├── README.md
│
├── model/
│   ├── Droop_control_conditioning_untouched.slx   pristine, never modified
│   └── Droop_control_conditioning_claude.slx      working copy, rebuilt by script
│
├── scripts/
│   ├── project_root.m          resolves paths from anywhere
│   ├── build_sweep_model.m     builds the working copy from the untouched one
│   ├── extract_features.m      waveforms -> scalar features (RMS window)
│   ├── run_pilot.m             15 diagnostic runs
│   ├── run_sweep.m             one slice of the 4704-run sweep
│   ├── verify_rebuild.m        checks a rebuild did not move the numbers
│   ├── make_run_list.py        writes data/run_list.csv
│   ├── merge_results.py        worker files -> dataset, validated
│   ├── make_pilot_xlsx.py      pilot results -> Excel
│   └── train_model.py          stage 2: the fault-diagnosis model
│
├── data/
│   ├── run_list.csv            4704 runs: the plan (inputs filled, outputs blank)
│   ├── raw/                    sweep_part1..4.csv, one per worker
│   ├── dataset.csv             28 columns, the schema as fixed by the guide
│   ├── dataset_extended.csv    34 columns, adds the 6 DC-offset features
│   └── diagnostics.csv         per-run health record
│
├── pilot/                      pilot_results.csv/.xlsx, waveforms, log
├── docs/                       Microgrid_Dataset_Schema.xlsx
├── results/                    model metrics
└── logs/                       sweep_w1..4.log
```

`slprj/`, `cache_w*/` and `*.slxc` are Simulink build caches. They regenerate
automatically and can be deleted at any time.

The project deliberately lives outside OneDrive. OneDrive syncing a folder
that four MATLAB processes append to every few seconds caused repeated file
locks, and a venv inside it would be ~20k files syncing continuously.

## Python environment

The venv also lives outside the project, for the same reason:

```bash
python -m venv C:\Users\prasa\venvs\microgrid
C:\Users\prasa\venvs\microgrid\Scripts\activate      # PowerShell
pip install -r requirements.txt
```

Nothing is installed into the system Python — activate the venv before running
any of the `.py` scripts.

## How to run it

```matlab
>> setup_paths                  % once per MATLAB session
>> build_sweep_model            % rebuild the working model from the untouched one
>> run_pilot                    % 15 diagnostic runs, ~2 min
```

```bash
python scripts/make_run_list.py     # regenerate the run list (deterministic)
```

Then the sweep, one of these in each of four MATLAB windows:

```matlab
>> run_sweep(1,4)   >> run_sweep(2,4)   >> run_sweep(3,4)   >> run_sweep(4,4)
```

Each worker writes its own file and flushes every row before the next
simulation, so it is safe to kill and restart — it resumes where it stopped.
Finally:

```bash
python scripts/merge_results.py    # merge, validate, write the three data files
```

## Stage 2 — the fault-diagnosis model

```bash
python scripts/train_model.py                        # dataset_extended.csv
python scripts/train_model.py data/dataset.csv       # 28-column schema only
```

**Input:** `Vabc` and `Iabc` at both buses — twelve RMS values.
**Output:** which PWM pulse is open, and the per-phase load resistances.

Two heads on the same features:

*Fault head* — formulated as **two 7-class problems** (per inverter: healthy,
or one of pulses 1–6) rather than twelve independent binary flags. The rule is
that at most one pulse is open per inverter, and a 7-class formulation encodes
that structurally: it cannot predict two open pulses on one inverter, which
twelve independent flags would happily do. The twelve 1/0 flags are
reconstructed from the predicted class for reporting.

*Load head* — regression on `R_a`, `R_b`, `R_c`, plus the degree of unbalance
derived from them (NEMA-style: maximum deviation from the mean, as a percent).

**The split matters more than the model.** Every load setting appears 49 times,
once per PWM state. A random row split would put 49 near-identical siblings of
every test row into training and report accuracy that is almost pure leakage.
Rows are grouped by load setting and whole groups are held out, so the test set
contains load conditions never seen during training.

The script trains on both feature sets and prints the difference, which turns
the open question below into a measured result rather than an argument.

## Design decisions worth knowing

**Two permitted variations only.** Per-phase load resistance (balanced, or
unbalanced by changing one or two phases) and open-switch faults (at most one
open pulse per inverter, the two inverters independent). That gives 96 load
settings × 49 PWM states = **4704 runs**, with all 49 fault classes exactly
balanced at 96 runs each.

**Only load bank A is varied.** Banks A and B sit on DG1's bus, bank C on
DG2's. Bank B is behind a breaker that closes at t=1 s, and runs stop at
0.4 s, so bank B never participates.

**The `InitFcn` is guarded.** It re-runs at every simulation start and would
otherwise overwrite anything set by `setVariable`, silently producing 4704
identical rows. The pilot verifies the guard works before any sweep runs.

**Scopes are commented out in the working copy.** 39 Scope/Display blocks cost
about half the runtime and cannot affect the result — verified identical to
1.7e-15 relative. Use `build_sweep_model(true)` to keep them, or open the
untouched model.

**The RMS window is sized from measured frequency.** Droop makes the
steady-state frequency load-dependent (~49.985 Hz, not 50). Averaging over a
window that is not a whole number of cycles leaves a residue that varies with
load — i.e. correlated with the regression target.

## Known open question

On the 28-column schema, **upper and lower switch faults on the same leg are
almost indistinguishable**. RMS discards sign, so a current missing its
positive half-cycle and one missing its negative half have nearly identical
RMS: the closest pair sits 0.0277 apart against a feature magnitude of 563.
That collapses 49 classes to roughly 16.

The DC offset of each inverter's phase currents separates them cleanly — the
same two cases sit 17.9 apart, about 650× more discriminative. This is why
`dataset_extended.csv` exists. Which file to use needs the guide's decision;
both come from the same runs, so nothing has to be re-simulated.

## Measured pulse-to-IGBT mapping

Not the textbook ordering. Determined empirically, identical on both
inverters — see `pilot/pilot_results.xlsx`, sheet "Pulse Mapping".

| Pulse | Leg | Half-cycle lost | Device |
|---|---|---|---|
| 1 | b | negative | lower |
| 2 | b | positive | upper |
| 3 | c | negative | lower |
| 4 | c | positive | upper |
| 5 | a | negative | lower |
| 6 | a | positive | upper |

## Environment

MATLAB R2024b, Simulink, Simscape Electrical. No Parallel Computing Toolbox
(so no `parsim` — parallelism is separate MATLAB processes), no Simulink Coder
(no rapid accelerator), no DSP System Toolbox (which is why the dangling `RMS`
block has to be commented out for the model to compile at all).
