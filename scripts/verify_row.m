function verify_row(runId, tol)
%VERIFY_ROW  Re-simulate one dataset row and compare every number.
%
%   verify_row(8)          re-run run_id 8 and compare against the dataset
%   verify_row(8, 1e-6)    with a custom tolerance
%
%   This is the definitive check: it takes the conditions recorded in the
%   dataset, runs the model again from scratch, extracts the features with the
%   same code the sweep used, and prints the two side by side.
%
%   THE TRAP THIS AVOIDS. The model's InitFcn is deliberately guarded with
%   ~exist so that values pushed in from outside survive it. That is what makes
%   the sweep work, but it also means a variable left in your base workspace
%   from a previous run will be SILENTLY REUSED. Set R_A_a = 16 by hand, run,
%   then try to run the default 32 ohm case and you will still get 16 ohm - with
%   no warning. This function clears the five swept variables before every run,
%   so each one starts clean.
%
%   To watch the waveforms while you do this, rebuild with the scopes live:
%       build_sweep_model(true)
%   That is about 2x slower and changes no numbers (verified to 1.7e-15).

if nargin < 2 || isempty(tol), tol = 1e-6; end

root = project_root();
mdl  = 'Droop_control_conditioning_claude';
NCYC = 4;

%% ---- find the row ------------------------------------------------------
csv = fullfile(root, 'data', 'dataset_full.csv');
assert(isfile(csv), 'no dataset at %s', csv);
T = readtable(csv);
k = find(T.run_id == runId, 1);
assert(~isempty(k), 'run_id %d is not in the dataset', runId);
r = T(k, :);

F1 = [r.DG1_PWM1 r.DG1_PWM2 r.DG1_PWM3 r.DG1_PWM4 r.DG1_PWM5 r.DG1_PWM6];
F2 = [r.DG2_PWM1 r.DG2_PWM2 r.DG2_PWM3 r.DG2_PWM4 r.DG2_PWM5 r.DG2_PWM6];

fprintf('\n=== run_id %d ===\n', runId);
fprintf('  load      R = %g / %g / %g ohm\n', r.R_a, r.R_b, r.R_c);
fprintf('  DG1 mask  [%s]%s\n', num2str(F1), describe(F1));
fprintf('  DG2 mask  [%s]%s\n', num2str(F2), describe(F2));

%% ---- clear the guarded variables, then re-run --------------------------
% Without this, anything left over in the base workspace wins silently.
evalin('base', 'clear R_A_a R_A_b R_A_c F1 F2');

load_system(fullfile(root, 'model', [mdl '.slx']));
in = Simulink.SimulationInput(mdl);
in = in.setVariable('R_A_a', r.R_a);
in = in.setVariable('R_A_b', r.R_b);
in = in.setVariable('R_A_c', r.R_c);
in = in.setVariable('F1', F1);
in = in.setVariable('F2', F2);

fprintf('\n  simulating...\n');
t0  = tic;
out = sim(in);
fprintf('  done in %.1f s\n', toc(t0));
close_system(mdl, 0);

f = extract_features(out, NCYC);

%% ---- compare -----------------------------------------------------------
names = fieldnames(f);
names = names(ismember(names, T.Properties.VariableNames));

fprintf('\n  %-12s %16s %16s %12s\n', 'feature', 'stored', 're-simulated', 'difference');
fprintf('  %s\n', repmat('-', 1, 60));

worst = 0; worstName = ''; nbad = 0;
for i = 1:numel(names)
    nm  = names{i};
    a   = r.(nm);
    b   = f.(nm);
    d   = abs(a - b);
    rel = d / max(abs(a), eps);
    if rel > worst, worst = rel; worstName = nm; end
    if rel > tol, nbad = nbad + 1; end
    % print the twelve dataset columns in full, the rest only if they differ
    isMain = any(strcmp(nm, {'V1_a','V1_b','V1_c','I1_a','I1_b','I1_c', ...
                             'V2_a','V2_b','V2_c','I2_a','I2_b','I2_c'}));
    if isMain || rel > tol
        fprintf('  %-12s %16.6f %16.6f %12.2e%s\n', nm, a, b, d, ...
                repmat(' <-- DIFFERS', 1, rel > tol));
    end
end

fprintf('\n  compared %d features\n', numel(names));
fprintf('  worst relative difference: %.2e  (%s)\n', worst, worstName);
if nbad == 0
    fprintf('\n  MATCH. The row was produced by this model at these settings.\n\n');
else
    fprintf('\n  %d feature(s) differ by more than %.0e - investigate.\n\n', ...
            nbad, tol);
end
end


function s = describe(mask)
k = find(mask == 0);
if isempty(k)
    s = '  (healthy)';
else
    legs = {'b','b','c','c','a','a'};
    dev  = {'lower','upper','lower','upper','lower','upper'};
    s = sprintf('  (pulse %d open = leg %s %s switch)', k, legs{k}, dev{k});
end
end
