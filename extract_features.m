function f = extract_features(out, ncyc)
%EXTRACT_FEATURES  Reduce one simulation's logged waveforms to scalar features.
%
%   f = EXTRACT_FEATURES(out, ncyc) takes the SimulationOutput from one run
%   and returns a struct of scalars computed over the LAST ncyc fundamental
%   cycles of the run.
%
%   Why the window is sized from f1 rather than assumed to be 1/50 s:
%   droop control makes the steady-state frequency load-dependent
%   (f = fn - m1*P), so it sits near 49.98 Hz, not 50. Averaging over a
%   window that is not a whole number of cycles leaves a fractional-cycle
%   residue, and the size of that residue changes with load - i.e. it would
%   correlate with R_a/R_b/R_c, the very thing being regressed. Sizing the
%   window as ncyc/f removes it.
%
%   Returned fields:
%     V1_a..c I1_a..c V2_a..c I2_a..c   true RMS  (the 28-column schema)
%     I1mean_a..c I2mean_a..c           DC offset (separates upper/lower)
%     f1 f2 P1 P2 Q1 Q2                 diagnostics, not dataset columns

ls = out.logsout;
gv = @(n) ls.getElement(n).Values;

% --- settled droop frequency, from the last 10% of the run --------------
f1v  = gv('f1').Data;
tail = round(0.9*numel(f1v)):numel(f1v);
fhz  = mean(f1v(tail));

% --- the averaging window: a whole number of fundamental cycles ---------
t   = gv('V1').Time;
sel = t >= t(end) - ncyc/fhz;

rms3 = @(d) sqrt(mean(d(sel,:).^2, 1));

V1 = gv('V1').Data;   I1 = gv('I1').Data;
V2 = gv('V2').Data;   I2 = gv('I2').Data;

% --- true RMS: includes switching ripple and harmonics, as a meter reads
f = phases(struct(), 'V1', rms3(V1));
f = phases(f, 'I1', rms3(I1));
f = phases(f, 'V2', rms3(V2));
f = phases(f, 'I2', rms3(I2));

% --- DC offset: the sign information that RMS throws away ---------------
f = phases(f, 'I1mean', mean(I1(sel,:), 1));
f = phases(f, 'I2mean', mean(I2(sel,:), 1));

% --- diagnostics --------------------------------------------------------
f.f1 = fhz;
f.f2 = mean(gv('f2').Data(tail));
f.P1 = mean(gv('P1').Data(sel));
f.P2 = mean(gv('P2').Data(sel));
f.Q1 = mean(gv('Q1').Data(sel));
f.Q2 = mean(gv('Q2').Data(sel));
end


function s = phases(s, name, v)
%PHASES  expand a 1x3 phase vector into _a/_b/_c scalar fields.
ph = {'a','b','c'};
for k = 1:3
    s.([name '_' ph{k}]) = v(k);
end
end
