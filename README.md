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
│   └── make_pilot_xlsx.py      pilot results -> Excel
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
└── logs/                       sweep_w1..4.log
```

`slprj/`, `cache_w*/` and `*.slxc` are Simulink build caches. They regenerate
automatically and can be deleted at any time.

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
