function run_sweep(worker, nworkers, maxRuns)
%RUN_SWEEP  Execute a slice of the 4704-run sweep.
%
%   run_sweep()                  run everything in this process
%   run_sweep(w, n)              run slice w of n  (w = 1..n)
%   run_sweep(w, n, maxRuns)     stop after maxRuns sims (for verification)
%
%   To split across four MATLAB windows, run one of these in each:
%       run_sweep(1,4)   run_sweep(2,4)   run_sweep(3,4)   run_sweep(4,4)
%   Each writes its own sweep_part<w>.csv; merge_results.py combines them.
%
%   Safety properties, which matter because this is a multi-hour job:
%
%     RESUMABLE  Every row is written and the file closed before the next
%                simulation starts. Re-running the same worker reads back
%                which run_ids are already present and skips them, so a
%                crash, a reboot, or closing the laptop costs one run.
%
%     ISOLATED   A run that fails to converge is caught, recorded as a NaN
%                row with ok=0, and logged to sweep_errors_<w>.log. The
%                sweep continues. You get a list of failures to inspect
%                rather than a stopped job.
%
%     SPLIT ON LOAD BOUNDARIES  run_list.csv holds 49 consecutive PWM states
%                per load setting. Workers take whole load blocks round
%                robin, so each keeps its 49 states contiguous.

if nargin < 1 || isempty(worker),   worker   = 1;   end
if nargin < 2 || isempty(nworkers), nworkers = 1;   end
if nargin < 3,                      maxRuns  = inf; end

MDL       = 'Droop_control_conditioning_claude';
NCYC      = 4;                                  % RMS window, cycles
PER_LOAD  = 49;                                 % PWM states per load setting
OUTFILE   = sprintf('sweep_part%d.csv', worker);
ERRFILE   = sprintf('sweep_errors_%d.log', worker);

%% ---- which runs belong to this worker --------------------------------
R = readtable('run_list.csv');
loadIdx = floor((R.run_id - 1) / PER_LOAD);
mine    = find(mod(loadIdx, nworkers) == worker - 1);

%% ---- skip anything already done --------------------------------------
done = [];
if isfile(OUTFILE)
    try
        prev = readtable(OUTFILE);
        done = prev.run_id;
    catch
        warning('could not read %s; starting fresh', OUTFILE);
    end
end
todo = mine(~ismember(R.run_id(mine), done));
if numel(todo) > maxRuns, todo = todo(1:maxRuns); end

fprintf('=== worker %d of %d ===\n', worker, nworkers);
fprintf('    assigned %d runs, %d already done, %d to do\n', ...
        numel(mine), numel(done), numel(todo));
if isempty(todo), fprintf('    nothing to do.\n'); return; end

COLS = columnNames();
if ~isfile(OUTFILE)
    fid = fopen(OUTFILE, 'w');
    fprintf(fid, '%s\n', strjoin(COLS, ','));
    fclose(fid);
end

% Each worker gets its own accelerator cache. Four MATLAB processes sharing
% one slprj folder can collide while building or reading the target; the
% cost of isolating them is one extra build per worker, about 40 s.
if nworkers > 1
    cf = fullfile(pwd, sprintf('cache_w%d', worker));
    if ~isfolder(cf), mkdir(cf); end
    Simulink.fileGenControl('set', 'CacheFolder', cf, 'CodeGenFolder', cf);
    fprintf('    accelerator cache: %s\n', cf);
end

load_system(MDL);
t_start = tic;
times   = [];

for i = 1:numel(todo)
    k = todo(i);
    r = R(k, :);

    F1 = [r.DG1_PWM1 r.DG1_PWM2 r.DG1_PWM3 r.DG1_PWM4 r.DG1_PWM5 r.DG1_PWM6];
    F2 = [r.DG2_PWM1 r.DG2_PWM2 r.DG2_PWM3 r.DG2_PWM4 r.DG2_PWM5 r.DG2_PWM6];

    in = Simulink.SimulationInput(MDL);
    in = in.setVariable('R_A_a', r.R_a);
    in = in.setVariable('R_A_b', r.R_b);
    in = in.setVariable('R_A_c', r.R_c);
    in = in.setVariable('F1', F1);
    in = in.setVariable('F2', F2);

    t0 = tic;
    try
        out = sim(in);
        f   = extract_features(out, NCYC);
        ok  = 1;
    catch ME
        f  = nanFeatures();
        ok = 0;
        fid = fopen(ERRFILE, 'a');
        fprintf(fid, 'run_id %d: %s | %s\n', r.run_id, ME.identifier, ME.message);
        fclose(fid);
    end
    el = toc(t0);
    times(end+1) = el; %#ok<AGROW>

    % ---- append immediately, then close, so a crash costs one run -----
    vals = [r.run_id, r.R_a, r.R_b, r.R_c, F1, F2, ...
            featureVector(f), el, ok];
    fid = fopen(OUTFILE, 'a');
    fprintf(fid, '%s\n', strjoin(compose('%.10g', vals), ','));
    fclose(fid);

    if mod(i, 10) == 0 || i == numel(todo) || i == 1
        rate = mean(times);
        left = (numel(todo) - i) * rate;
        fprintf('  %5d/%-5d  run_id %-5d  %4.1fs  elapsed %5.1f min  eta %5.1f min\n', ...
                i, numel(todo), r.run_id, el, toc(t_start)/60, left/60);
    end
end

close_system(MDL, 0);
fprintf('\nworker %d finished %d runs in %.1f min (mean %.1f s/run)\n', ...
        worker, numel(todo), toc(t_start)/60, mean(times));
if isfile(ERRFILE)
    fprintf('*** failures were logged to %s - check it ***\n', ERRFILE);
end
end

% ======================================================================
function c = columnNames()
c = [{'run_id','R_a','R_b','R_c'}, ...
     arrayfun(@(k) sprintf('DG1_PWM%d',k), 1:6, 'uni', 0), ...
     arrayfun(@(k) sprintf('DG2_PWM%d',k), 1:6, 'uni', 0), ...
     featureNames(), {'wall_s','ok'}];
end

function n = featureNames()
%FEATURENAMES  order must match featureVector exactly.
p = {'a','b','c'};
n = {};
for base = {'V1','I1','V2','I2','I1mean','I2mean'}
    for k = 1:3, n{end+1} = [base{1} '_' p{k}]; end %#ok<AGROW>
end
n = [n, {'f1','f2','P1','P2','Q1','Q2'}];
end

function v = featureVector(f)
n = featureNames();
v = zeros(1, numel(n));
for k = 1:numel(n), v(k) = f.(n{k}); end
end

function f = nanFeatures()
n = featureNames();
f = struct();
for k = 1:numel(n), f.(n{k}) = NaN; end
end
