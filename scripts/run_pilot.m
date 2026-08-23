function run_pilot()
%RUN_PILOT  15 diagnostic runs before committing to the 4704-run sweep.
%
%   Answers four questions, in order of how badly a wrong answer would hurt:
%
%   Q1  Does setVariable actually reach the model, or does InitFcn still
%       overwrite it?  Cases 14-15 change the load. If their currents match
%       case 1, the guard failed and the whole sweep would be 4704 identical
%       rows. This is the single most important check here.
%
%   Q2  Does an open pulse produce a visible change at all?
%
%   Q3  Which pulse number drives which IGBT?  An open UPPER switch kills the
%       positive half-cycle of that phase's current; an open LOWER switch
%       kills the negative half. Comparing positive-half RMS against
%       negative-half RMS per phase identifies both the leg and the half.
%
%   Q4  Do the 13 fault states actually look different from each other after
%       RMS averaging?  If upper and lower faults on the same leg collapse to
%       the same RMS signature, 49 classes is really 25 and the sweep design
%       needs revisiting BEFORE spending 10 hours on it.
%
%   Writes pilot_results.csv and pilot_waveforms.mat.

root = project_root();
mdl  = 'Droop_control_conditioning_claude';
NCYC = 4;                      % RMS window, in fundamental cycles

%% ---- case list -------------------------------------------------------
C = struct('desc',{},'R',{},'F1',{},'F2',{});
H = [1 1 1 1 1 1];
C(end+1) = mk('healthy, balanced 32', [32 32 32], H, H);
for k = 1:6
    C(end+1) = mk(sprintf('DG1 pulse %d open', k), [32 32 32], openp(k), H); %#ok<AGROW>
end
for k = 1:6
    C(end+1) = mk(sprintf('DG2 pulse %d open', k), [32 32 32], H, openp(k)); %#ok<AGROW>
end
% guard checks: same fault state as case 1, different load
C(end+1) = mk('healthy, balanced 64  [GUARD]', [64 64 64], H, H);
C(end+1) = mk('healthy, a=16 unbal   [GUARD]', [16 32 32], H, H);

fprintf('=== pilot: %d runs ===\n\n', numel(C));
load_system(fullfile(root,'model',[mdl '.slx']));
R = table();

for i = 1:numel(C)
    in = Simulink.SimulationInput(mdl);
    in = in.setVariable('R_A_a', C(i).R(1));
    in = in.setVariable('R_A_b', C(i).R(2));
    in = in.setVariable('R_A_c', C(i).R(3));
    in = in.setVariable('F1', C(i).F1);
    in = in.setVariable('F2', C(i).F2);

    t0 = tic;
    try
        out = sim(in);
        el  = toc(t0);
        row = extract(out, NCYC);
        row.ok = true;  row.err = "";
        WAVE(i) = struct('desc', C(i).desc, ...
                         'I1', row.wI1, 'I2', row.wI2, 't', row.wt); %#ok<AGROW>
    catch ME
        el  = toc(t0);
        row = emptyrow();
        row.ok = false;  row.err = string(ME.message);
        WAVE(i) = struct('desc', C(i).desc, 'I1', [], 'I2', [], 't', []); %#ok<AGROW>
        fprintf('  !! case %d FAILED: %s\n', i, ME.message);
    end

    row.case = i;
    row.desc = string(C(i).desc);
    row.R_A_a = C(i).R(1); row.R_A_b = C(i).R(2); row.R_A_c = C(i).R(3);
    row.F1 = mat2str(C(i).F1);  row.F2 = mat2str(C(i).F2);
    row.wall_s = el;
    row = rmfield(row, {'wI1','wI2','wt'});
    R = [R; struct2table(row)]; %#ok<AGROW>

    fprintf('%2d/%2d  %-32s  %5.1fs\n', i, numel(C), C(i).desc, el);
end

close_system(mdl, 0);
writetable(R, fullfile(root,'pilot','pilot_results.csv'));
save(fullfile(root,'pilot','pilot_waveforms.mat'), 'WAVE', '-v7.3');
report(R);
end

% ======================================================================
function s = mk(d, R, F1, F2)
s = struct('desc', d, 'R', R, 'F1', F1, 'F2', F2);
end

function m = openp(k)
m = ones(1,6);  m(k) = 0;
end

function r = emptyrow()
n = nan(1,3);
r = struct('V1',n,'I1',n,'V2',n,'I2',n, 'f1',nan,'f2',nan, ...
           'P1',nan,'P2',nan,'Q1',nan,'Q2',nan, ...
           'I1mean',n,'I1pos',n,'I1neg',n,'I2mean',n,'I2pos',n,'I2neg',n, ...
           'wI1',[], 'wI2',[], 'wt',[]);
r = flatten(r);
end

function r = extract(out, ncyc)
ls = out.logsout;
gv = @(n) ls.getElement(n).Values;

f1v = gv('f1').Data;  tail = round(0.9*numel(f1v)):numel(f1v);
f   = mean(f1v(tail));

t    = gv('V1').Time;
sel  = t >= t(end) - ncyc/f;          % exact whole number of cycles
rms3 = @(d) sqrt(mean(d(sel,:).^2, 1));

I1d = gv('I1').Data;  I2d = gv('I2').Data;

r.V1 = rms3(gv('V1').Data);   r.I1 = rms3(I1d);
r.V2 = rms3(gv('V2').Data);   r.I2 = rms3(I2d);
r.f1 = f;                     r.f2 = mean(gv('f2').Data(tail));
r.P1 = mean(gv('P1').Data(sel));  r.P2 = mean(gv('P2').Data(sel));
r.Q1 = mean(gv('Q1').Data(sel));  r.Q2 = mean(gv('Q2').Data(sel));

% half-cycle asymmetry: this is what identifies upper vs lower switch
[r.I1mean, r.I1pos, r.I1neg] = halves(I1d(sel,:));
[r.I2mean, r.I2pos, r.I2neg] = halves(I2d(sel,:));

r.wI1 = single(I1d(sel,:));  r.wI2 = single(I2d(sel,:));  r.wt = single(t(sel));
r = flatten(r);
end

function [mn, rp, rn] = halves(d)
%HALVES  per-column mean, positive-half RMS, negative-half RMS.
mn = mean(d, 1);
rp = zeros(1,size(d,2));  rn = rp;
for c = 1:size(d,2)
    p = d(d(:,c) > 0, c);   n = d(d(:,c) < 0, c);
    rp(c) = sqrt(mean(p.^2));  if isempty(p), rp(c) = 0; end
    rn(c) = sqrt(mean(n.^2));  if isempty(n), rn(c) = 0; end
end
end

function r = flatten(s)
%FLATTEN  expand 1x3 phase vectors into _a/_b/_c scalar fields for the table.
r = struct();
for fn = string(fieldnames(s))'
    v = s.(fn);
    if isnumeric(v) && isequal(size(v), [1 3])
        ph = {'a','b','c'};
        for k = 1:3, r.(fn + "_" + ph{k}) = v(k); end
    else
        r.(fn) = v;
    end
end
end

% ======================================================================
function report(R)
fprintf('\n\n================= PILOT REPORT =================\n');

ok = R.ok;
fprintf('\nruns completed: %d / %d\n', sum(ok), height(R));
if any(~ok)
    fprintf('FAILURES:\n');
    disp(R(~ok, {'case','desc','err'}));
end

%% Q1 - did setVariable survive InitFcn?
fprintf('\n--- Q1: does setVariable reach the model? ---\n');
b = R(R.case==1,:);  g1 = R(R.case==14,:);  g2 = R(R.case==15,:);
fprintf('  case  1  R=[32 32 32]  I1 = %7.3f %7.3f %7.3f\n', b.I1_a, b.I1_b, b.I1_c);
fprintf('  case 14  R=[64 64 64]  I1 = %7.3f %7.3f %7.3f\n', g1.I1_a, g1.I1_b, g1.I1_c);
fprintf('  case 15  R=[16 32 32]  I1 = %7.3f %7.3f %7.3f\n', g2.I1_a, g2.I1_b, g2.I1_c);
d14 = abs(g1.I1_a - b.I1_a);  d15 = abs(g2.I1_a - b.I1_a);
if d14 < 1e-6 || d15 < 1e-6
    fprintf('  *** FAIL: load change had NO effect. InitFcn is still\n');
    fprintf('  *** overwriting setVariable. DO NOT RUN THE SWEEP.\n');
else
    fprintf('  PASS: load changes move the current (%.3f A and %.3f A).\n', d14, d15);
    fprintf('        case 15 should also break phase symmetry - check above.\n');
end

%% Q2/Q3 - fault visibility and pulse mapping
fprintf('\n--- Q2/Q3: fault signature and pulse -> IGBT mapping ---\n');
fprintf('  For the faulted inverter, per phase: mean current, and the ratio\n');
fprintf('  of positive-half RMS to negative-half RMS.\n');
fprintf('  ratio >> 1 => negative half suppressed => LOWER switch open\n');
fprintf('  ratio << 1 => positive half suppressed => UPPER switch open\n\n');
fprintf('  %-22s %-24s %s\n', 'case', 'mean I (a,b,c)', 'pos/neg RMS ratio (a,b,c)');
for i = [1 2:7 8:13]
    r = R(R.case==i,:);
    if ~r.ok, continue; end
    if i >= 8, mn = [r.I2mean_a r.I2mean_b r.I2mean_c];
               rp = [r.I2pos_a r.I2pos_b r.I2pos_c];
               rn = [r.I2neg_a r.I2neg_b r.I2neg_c];
    else,      mn = [r.I1mean_a r.I1mean_b r.I1mean_c];
               rp = [r.I1pos_a r.I1pos_b r.I1pos_c];
               rn = [r.I1neg_a r.I1neg_b r.I1neg_c];
    end
    ratio = rp ./ max(rn, 1e-9);
    fprintf('  %-22s %7.3f %7.3f %7.3f   %7.2f %7.2f %7.2f\n', ...
            r.desc, mn, ratio);
end

%% Q4 - are the 13 states distinguishable?
fprintf('\n--- Q4: are the 13 states separable on RMS alone? ---\n');
V = [R.V1_a R.V1_b R.V1_c R.I1_a R.I1_b R.I1_c ...
     R.V2_a R.V2_b R.V2_c R.I2_a R.I2_b R.I2_c];
V = V(1:13, :);                       % the 13 fault states, same load
D = squareform_(pdist_(V));
D(1:size(D,1)+1:end) = inf;
[mn, idx] = min(D(:));
[i1, i2] = ind2sub(size(D), idx);
fprintf('  closest pair: case %d (%s)\n           and case %d (%s)\n', ...
        i1, R.desc(i1), i2, R.desc(i2));
fprintf('  euclidean distance between their 12 RMS features: %.4f\n', mn);
sc = norm(V(1,:));
fprintf('  as a fraction of the healthy feature magnitude:   %.2e\n', mn/sc);
if mn/sc < 1e-3
    fprintf('  *** WARNING: two states are nearly identical on RMS features.\n');
    fprintf('  *** 49 classes may not be separable. Review before sweeping.\n');
else
    fprintf('  OK: all 13 states are distinguishable on RMS alone.\n');
end
fprintf('\n===============================================\n');
end

function D = pdist_(X)
n = size(X,1);  D = [];
for i = 1:n-1
    for j = i+1:n, D(end+1) = norm(X(i,:)-X(j,:)); end %#ok<AGROW>
end
end

function M = squareform_(v)
n = round((1+sqrt(1+8*numel(v)))/2);  M = zeros(n);  k = 1;
for i = 1:n-1
    for j = i+1:n, M(i,j) = v(k); M(j,i) = v(k); k = k+1; end
end
end
