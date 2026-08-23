function f = extract_features(out, ncyc)
%EXTRACT_FEATURES  Reduce one simulation's logged waveforms to scalar features.
%
%   f = EXTRACT_FEATURES(out, ncyc) takes the SimulationOutput from one run
%   and returns a struct of scalars computed over the LAST ncyc fundamental
%   cycles of the run.
%
%   Three families of feature, because the two prediction tasks need
%   different things and no single reduction serves both:
%
%   1. TRUE RMS  (V1_a.. I2_c)
%      Includes every harmonic - what a meter reads. Carries the distortion
%      an open switch produces, which is signal for the fault task.
%
%   2. DC OFFSET (I1mean_a.. I2mean_c)
%      RMS squares the signal and so discards sign. A current missing its
%      positive half-cycle and one missing its negative half have almost
%      identical RMS, which makes upper and lower switch faults on the same
%      leg nearly indistinguishable. The mean separates them cleanly.
%
%   3. FUNDAMENTAL PHASOR (V1f_a.. I2f_c magnitudes, V1ang_a.. I2ang_c angles)
%      For the load task. The load is a pure resistor and therefore linear,
%      so at the fundamental I = V/R holds exactly however distorted the
%      total waveform is - all the distortion sits in other harmonics.
%      The ANGLE is not optional: bank A is fed by both inverters, so
%      recovering its resistance means adding two currents, and currents add
%      as phasors, not as magnitudes. Measured on this model, recovering a
%      48/24/96 ohm bank under a double fault gives
%          true RMS            11.8 / 17.3 /  9.8   (useless)
%          fundamental mag     33.9 / 19.0 / 31.3   (still wrong)
%          fundamental phasor  48.0 / 24.0 / 96.1   (exact)
%
%   Angles are referenced to V1_a, so only relative phase is stored. The
%   absolute angle depends on where the averaging window happens to fall,
%   which shifts with the droop frequency and carries no physical meaning.
%
%   Why the window is sized from f1 rather than assumed to be 1/50 s:
%   droop control makes the steady-state frequency load-dependent
%   (f = fn - m1*P), so it sits near 49.98 Hz, not 50. Averaging over a
%   window that is not a whole number of cycles leaves a fractional-cycle
%   residue whose size changes with load - i.e. it would correlate with
%   R_a/R_b/R_c, the very thing being regressed.

ls = out.logsout;
gv = @(n) ls.getElement(n).Values;

% --- settled droop frequency, from the last 10% of the run --------------
f1v  = gv('f1').Data;
tail = round(0.9*numel(f1v)):numel(f1v);
fhz  = mean(f1v(tail));

% --- the averaging window: a whole number of fundamental cycles ---------
t   = gv('V1').Time;
sel = t >= t(end) - ncyc/fhz;
tw  = t(sel);

rms3 = @(d) sqrt(mean(d(sel,:).^2, 1));

V1 = gv('V1').Data;   I1 = gv('I1').Data;
V2 = gv('V2').Data;   I2 = gv('I2').Data;

% --- 1. true RMS --------------------------------------------------------
f = phases(struct(), 'V1', rms3(V1));
f = phases(f, 'I1', rms3(I1));
f = phases(f, 'V2', rms3(V2));
f = phases(f, 'I2', rms3(I2));

% --- 2. DC offset -------------------------------------------------------
f = phases(f, 'I1mean', mean(I1(sel,:), 1));
f = phases(f, 'I2mean', mean(I2(sel,:), 1));

% --- 3. fundamental phasors --------------------------------------------
pV1 = phasor(V1(sel,:), tw, fhz);
pI1 = phasor(I1(sel,:), tw, fhz);
pV2 = phasor(V2(sel,:), tw, fhz);
pI2 = phasor(I2(sel,:), tw, fhz);

ref = angle(pV1(1));                      % V1_a is the phase reference
wrap = @(p) mod(rad2deg(angle(p) - ref) + 180, 360) - 180;

f = phases(f, 'V1f', abs(pV1));   f = phases(f, 'V1ang', wrap(pV1));
f = phases(f, 'I1f', abs(pI1));   f = phases(f, 'I1ang', wrap(pI1));
f = phases(f, 'V2f', abs(pV2));   f = phases(f, 'V2ang', wrap(pV2));
f = phases(f, 'I2f', abs(pI2));   f = phases(f, 'I2ang', wrap(pI2));

% --- diagnostics --------------------------------------------------------
f.f1 = fhz;
f.f2 = mean(gv('f2').Data(tail));
f.P1 = mean(gv('P1').Data(sel));
f.P2 = mean(gv('P2').Data(sel));
f.Q1 = mean(gv('Q1').Data(sel));
f.Q2 = mean(gv('Q2').Data(sel));
end


function p = phasor(d, t, f)
%PHASOR  complex fundamental phasor per column, scaled to RMS magnitude.
%   Projection onto cos and sin at f. Exact when the window spans a whole
%   number of periods, which is how the window above is chosen.
w = 2*pi*f;
a = 2 * mean(d .* cos(w*t), 1);
b = 2 * mean(d .* sin(w*t), 1);
p = (a - 1j*b) / sqrt(2);
end


function s = phases(s, name, v)
%PHASES  expand a 1x3 phase vector into _a/_b/_c scalar fields.
ph = {'a','b','c'};
for k = 1:3
    s.([name '_' ph{k}]) = v(k);
end
end
