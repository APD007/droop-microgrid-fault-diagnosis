# Droop-controlled microgrid â€” fault diagnosis

B.Tech final-year project, electrical engineering.

Two parallel droop-controlled inverters in an islanded microgrid, simulated in
Simulink. The project has two stages:

1. **Dataset generation** â€” sweep the model over every permitted permutation of
   load unbalance and open-switch (IGBT) fault, and reduce each run to a row of
   RMS measurements. 10,584 runs.
2. **Fault diagnosis model** â€” train a model to recover the fault state (which
   pulse is open, on which inverter) and the per-phase load resistances from
   the measured voltages and currents alone.

Both stages are complete. The dataset passes ten independent physical checks;
the model scores 96.8 % on the 49 combined fault states with load settings it
has never seen, and recovers the load resistances to 0.003 Î©.

## Layout

```
.
â”œâ”€â”€ setup_paths.m           run this first in MATLAB, once per session
â”œâ”€â”€ requirements.txt        pinned Python dependencies
â”œâ”€â”€ README.md
â”‚
â”œâ”€â”€ model/
â”‚   â”œâ”€â”€ Droop_control_conditioning_untouched.slx   pristine, never modified
â”‚   â””â”€â”€ Droop_control_conditioning_claude.slx      working copy, rebuilt by script
â”‚
â”œâ”€â”€ scripts/
â”‚   â”œâ”€â”€ project_root.m          resolves paths from anywhere
â”‚   â”œâ”€â”€ build_sweep_model.m     builds the working copy from the untouched one
â”‚   â”œâ”€â”€ extract_features.m      waveforms -> scalar features (RMS window)
â”‚   â”œâ”€â”€ run_pilot.m             15 diagnostic runs
â”‚   â”œâ”€â”€ run_sweep.m             one slice of the 10,584-run sweep
â”‚   â”œâ”€â”€ verify_rebuild.m        checks a rebuild did not move the numbers
â”‚   â”œâ”€â”€ make_run_list.py        writes data/run_list.csv
â”‚   â”œâ”€â”€ merge_results.py        worker files -> dataset, validated
â”‚   â”œâ”€â”€ make_pilot_xlsx.py      pilot results -> Excel
â”‚   â”œâ”€â”€ features.py             SHARED feature definitions and derivation
â”‚   â”‚
â”‚   â”‚   -- the model --
â”‚   â”œâ”€â”€ train_model.py          compares feature sets on a held-out split
â”‚   â”œâ”€â”€ train_final.py          trains the shipped model on all rows
â”‚   â”œâ”€â”€ predict.py              >>> run the model on new data <<<
â”‚   â”‚
â”‚   â”‚   -- getting data in --
â”‚   â”œâ”€â”€ features_from_logs.m       Simulink run -> the CSV predict.py wants
â”‚   â”œâ”€â”€ features_from_waveforms.py sampled waveforms -> the same, no MATLAB
â”‚   â”œâ”€â”€ make_input_template.py     builds docs/model_input_template.xlsx
â”‚   â”‚
â”‚   â”‚   -- checking it --
â”‚   â”œâ”€â”€ verify_dataset.py       ten physical checks over every row
â”‚   â”œâ”€â”€ verify_row.m            re-simulate one row, compare all 42 features
â”‚   â”œâ”€â”€ validate_fundamental.m  why phasors, not magnitudes (the evidence)
â”‚   â”œâ”€â”€ make_offlattice_list.py held-out validation at unseen resistances
â”‚   â”œâ”€â”€ eval_offlattice.py      scores the model on those unseen resistances
â”‚   â”œâ”€â”€ noise_test.py           accuracy against measurement noise
â”‚   â””â”€â”€ make_figures.py         report figures
â”‚
â”œâ”€â”€ models/
â”‚   â”œâ”€â”€ fault_diagnosis.joblib  the trained model, ready to run
â”‚   â””â”€â”€ manifest.json           what it expects, and how it was built
â”‚
â”œâ”€â”€ data/
â”‚   â”œâ”€â”€ run_list.csv            the original 96-setting plan
â”‚   â”œâ”€â”€ run_list_extra.csv      the 120 settings that widened it to 216
â”‚   â”œâ”€â”€ run_list_offlattice.csv 12 settings at resistances never trained on
â”‚   â”œâ”€â”€ raw/                    sweep_part1..4 + sweep_extra_part1..4, per worker
â”‚   â”œâ”€â”€ dataset.csv             28 columns, the schema as originally fixed
â”‚   â”œâ”€â”€ dataset_extended.csv    34 columns, adds the 6 DC-offset features
â”‚   â”œâ”€â”€ dataset_full.csv        58 columns, everything  <-- the one to use
â”‚   â”œâ”€â”€ dataset_offlattice.csv  588 held-out validation rows
â”‚   â””â”€â”€ diagnostics.csv         per-run health record
â”‚
â”œâ”€â”€ pilot/                      pilot_results.csv/.xlsx, waveforms, log
â”œâ”€â”€ docs/                       schema workbook + model_input_template.xlsx
â”œâ”€â”€ results/                    metrics.json, noise_robustness.csv, figures/
â””â”€â”€ logs/                       sweep and noise-test logs
```

`slprj/`, `cache_w*/` and `*.slxc` are Simulink build caches. They regenerate
automatically and can be deleted at any time.

If the project folder is inside a cloud-sync directory, pause syncing before
running a sweep â€” four workers appending to CSVs after every run gives a
sync client a great deal to do, and it slows the sweep measurably.

## Python environment

The venv also lives outside the project, for the same reason:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Nothing is installed into the system Python â€” activate the venv before running
any of the `.py` scripts. Keep the venv out of any cloud-synced folder; it is
roughly 20,000 files.

## How to run it

```matlab
>> setup_paths                  % once per MATLAB session
>> build_sweep_model            % rebuild the working model from the untouched one
>> run_pilot                    % 15 diagnostic runs, ~2 min
```

```bash
python scripts/make_run_list.py       # the original 96 settings
python scripts/make_run_list_full.py  # the 120 that complete the 6^3 factorial
```

Then the sweep, one of these in each of four MATLAB windows:

```matlab
>> run_sweep(1,4)   >> run_sweep(2,4)   >> run_sweep(3,4)   >> run_sweep(4,4)
```

`run_sweep` takes an optional fourth argument naming a run list, so the
extension and validation sweeps reuse the same worker:

```matlab
>> run_sweep(1,4,inf,'_extra')        % reads run_list_extra.csv
>> run_sweep(1,4,inf,'_offlattice')   % reads run_list_offlattice.csv
```

Each worker writes its own file and flushes every row before the next
simulation, so it is safe to kill and restart â€” it resumes where it stopped.
Finally:

```bash
python scripts/merge_results.py    # merge, validate, write the three data files
```

## Testing the model on new data

This is the handover path. Two steps.

**In MATLAB** â€” run the model at whatever conditions you want to test, and
write out the measurements:

```matlab
setup_paths
in = Simulink.SimulationInput('Droop_control_conditioning_claude');
in = in.setVariable('R_A_a', 40);            % any values, on or off lattice
in = in.setVariable('R_A_b', 40);
in = in.setVariable('R_A_c', 72);
in = in.setVariable('F1', [1 1 0 1 1 1]);    % DG1 pulse 3 open
in = in.setVariable('F2', [1 1 1 1 1 1]);    % DG2 healthy
out = sim(in);
features_from_logs(out, 'my_test.csv');
```

**Then, in the shell:**

```bash
python scripts/predict.py my_test.csv
```

Out comes `my_test_predictions.csv` with the twelve PWM flags, `R_a/R_b/R_c`,
the degree of unbalance, and a confidence for each fault call. If the input
already carries the true answers, `predict.py` scores itself against them and
prints the result.

Several runs can be batched: pass an array of `SimulationOutput` objects to
`features_from_logs`, and every row lands in the same CSV.

`predict.py` refuses input it cannot use rather than producing a plausible
wrong answer â€” it names the missing columns and stops.

## Stage 2 â€” training

```bash
python scripts/train_model.py data/dataset_full.csv   # compare feature sets
python scripts/train_final.py                         # train + save the model
python scripts/noise_test.py                          # robustness sweep
python scripts/make_figures.py                        # report figures
```

## Checking the data is right

Nothing here has to be taken on trust.

```bash
python scripts/verify_dataset.py     # ten physical checks over all 10,584 rows
python scripts/eval_offlattice.py    # score at resistances never trained on
```

```matlab
verify_row(1324)    % re-simulate one row and compare all 42 features
```

`verify_dataset.py` tests laws the numbers must obey regardless of how they
were produced â€” Kirchhoff, Ohm, Parseval, the DC offsets summing to zero,
class balance, and the pulseâ†’leg mapping. A bug anywhere in the pipeline shows
up as a violation rather than hiding. All ten currently pass.

`verify_row` is the definitive check: it re-runs the model at a row's recorded
conditions and compares every feature. On `run_id 8` the worst relative
difference is 3.4e-10.

**If you do it by hand**, clear the swept variables first:

```matlab
clear R_A_a R_A_b R_A_c F1 F2
```

The `InitFcn` is guarded with `~exist` so that values pushed in from outside
survive it â€” that is what makes the sweep work, and it also means a leftover
variable is silently reused. Set `R_A_a = 16`, run, then try the default 32 Î©
case and you still get 16 Î©, with no warning.

**Input:** `Vabc` and `Iabc` at both buses â€” twelve RMS values.
**Output:** which PWM pulse is open, and the per-phase load resistances.

Two heads on the same features:

*Fault head* â€” formulated as **two 7-class problems** (per inverter: healthy,
or one of pulses 1â€“6) rather than twelve independent binary flags. The rule is
that at most one pulse is open per inverter, and a 7-class formulation encodes
that structurally: it cannot predict two open pulses on one inverter, which
twelve independent flags would happily do. The twelve 1/0 flags are
reconstructed from the predicted class for reporting.

*Load head* â€” **analytic, not learned.** `R = V1 / (I1 + I2 âˆ’ V2/160)` per
phase, every term a fundamental phasor, with `V1` and `V2` first stepped back
through the coupling impedance. The degree of unbalance is then derived from
the three resistances (NEMA: maximum deviation from the mean, as a percent).

A random forest was trained on the same targets and is kept in the model
bundle, but it is **not** what `predict.py` returns. A forest predicts by
averaging training leaf values, so it can only ever output resistances near
ones it has seen. Measured on 588 runs at resistances never trained on:

| | MAE | worst |
|---|---|---|
| analytic | **0.003 Î©** | 0.06 Î© |
| random forest | 3.7 Î© | 8.0 Î© |

The forest returns its nearest trained level â€” a true 72 Î© comes back as
exactly 64.000, a true 88 Î© as exactly 96.000. The analytic head returns
71.995 and 87.992. This is the single most important thing to understand
about the load head, and it is why the model can be tested at any resistance.

**The split matters more than the model.** Every load setting appears 49 times,
once per PWM state. A random row split would put 49 near-identical siblings of
every test row into training and report accuracy that is almost pure leakage.
Rows are grouped by load setting and whole groups are held out, so the test set
contains load conditions never seen during training.

The script trains on both feature sets and prints the difference, which turns
the open question below into a measured result rather than an argument.

## Design decisions worth knowing

**Two variations, enumerated completely.** Per-phase load resistance and
open-switch faults (at most one open pulse per inverter, the two inverters
independent). Each phase takes any of six levels `{16, 24, 32, 48, 64, 96} Î©`
independently, so the load axis is the full factorial 6Â³ = **216 settings** Ã—
49 PWM states = **10,584 runs**, with all 49 fault classes exactly balanced at
216 runs each.

The first sweep used a narrower rule â€” balanced, or one or two phases moved
away from a 32 Î© base â€” giving 96 settings and 4704 runs. That restriction was
dropped and the missing 120 settings simulated; the original 96 are a subset,
so only the new ones were run. Widening it raised fault accuracy from 94.9 % to
96.8 %, and the added cases are the hardest: with all three phases different
there is no reference phase for the model to lean on.

**Only load bank A is varied.** Banks A and B sit on DG1's bus, bank C on
DG2's. Bank B is behind a breaker that closes at t=1 s, and runs stop at
0.4 s, so bank B never participates.

**The `InitFcn` is guarded.** It re-runs at every simulation start and would
otherwise overwrite anything set by `setVariable`, silently producing 10,584
identical rows. The pilot verifies the guard works before any sweep runs.

**Scopes are commented out in the working copy.** 39 Scope/Display blocks cost
about half the runtime and cannot affect the result â€” verified identical to
1.7e-15 relative. Use `build_sweep_model(true)` to keep them, or open the
untouched model.

**The RMS window is sized from measured frequency.** Droop makes the
steady-state frequency load-dependent (~49.985 Hz, not 50). Averaging over a
window that is not a whole number of cycles leaves a residue that varies with
load â€” i.e. correlated with the regression target.

## Known open question

On the 28-column schema, **upper and lower switch faults on the same leg are
almost indistinguishable**. RMS discards sign, so a current missing its
positive half-cycle and one missing its negative half have nearly identical
RMS: the closest pair sits 0.0277 apart against a feature magnitude of 563.
That collapses 49 classes to roughly 16.

The DC offset of each inverter's phase currents separates them cleanly â€” the
same two cases sit 17.9 apart, about 650Ã— more discriminative. This is why
`dataset_extended.csv` exists. Which file to use needs the guide's decision;
both come from the same runs, so nothing has to be re-simulated.

## Measured pulse-to-IGBT mapping

Not the textbook ordering. Determined empirically, identical on both
inverters â€” see `pilot/pilot_results.xlsx`, sheet "Pulse Mapping".

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
(so no `parsim` â€” parallelism is separate MATLAB processes), no Simulink Coder
(no rapid accelerator), no DSP System Toolbox (which is why the dangling `RMS`
block has to be commented out for the model to compile at all).
