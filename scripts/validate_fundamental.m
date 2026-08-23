% Can bank A's resistance be recovered from the measurements under fault?
%
% Three ways of reducing each waveform, compared against the resistance that
% was actually set:
%
%   1. true RMS          - what the dataset currently stores
%   2. fundamental MAG   - fundamental component, magnitude only
%   3. fundamental PHASOR- fundamental component, magnitude AND angle
%
% Bank A is fed by both inverters: DG2 supplies its own bank C (fixed) and
% sends the remainder up the line, so I_bankA = I1 + (I2 - V2/R_C).
% That sum is a sum of SINUSOIDS, not of magnitudes. When everything is
% healthy the three currents happen to be nearly in phase and adding
% magnitudes is a decent approximation; under fault it is not, which is why
% magnitudes alone fail. Complex phasors add correctly.

mdl  = 'Droop_control_conditioning_claude';
NCYC = 4;
R_C  = 160;
Rset = [48 24 96];

root = project_root();
cand = {fullfile(root,'model',[mdl '.slx']), fullfile(root,[mdl '.slx'])};
found = cand(cellfun(@isfile, cand));
assert(~isempty(found), 'cannot find %s.slx', mdl);
load_system(found{1});

H = [1 1 1 1 1 1];
cases = { 'healthy',            H,               H
          'DG1 pulse 1 open',   [0 1 1 1 1 1],   H
          'DG1 pulse 3 open',   [1 1 0 1 1 1],   H
          'DG1 p1 + DG2 p4',    [0 1 1 1 1 1],   [1 1 1 0 1 1] };

fprintf('\nbank A actually set to R = [%g %g %g] ohm\n\n', Rset);
fprintf('%-19s %-20s %-20s %-20s\n', '', 'TRUE RMS', 'FUND. MAGNITUDE', 'FUND. PHASOR');
fprintf('%-19s %6s %6s %6s  %6s %6s %6s  %6s %6s %6s\n', 'case', ...
        'Ra','Rb','Rc','Ra','Rb','Rc','Ra','Rb','Rc');

for i = 1:size(cases,1)
    in = Simulink.SimulationInput(mdl);
    in = in.setVariable('R_A_a',Rset(1));
    in = in.setVariable('R_A_b',Rset(2));
    in = in.setVariable('R_A_c',Rset(3));
    in = in.setVariable('F1',cases{i,2});
    in = in.setVariable('F2',cases{i,3});
    out = sim(in);

    ls = out.logsout;
    gv = @(n) ls.getElement(n).Values;
    f1v = gv('f1').Data;  tail = round(0.9*numel(f1v)):numel(f1v);
    f   = mean(f1v(tail));
    t   = gv('V1').Time;
    sel = t >= t(end) - NCYC/f;
    tw  = t(sel);

    rms3 = @(nm) sqrt(mean(gv(nm).Data(sel,:).^2, 1));
    ph3  = @(nm) phasor(gv(nm).Data(sel,:), tw, f);

    recover = @(V1,I1,V2,I2) V1 ./ (I1 + I2 - V2/R_C);

    Rrms  = recover(rms3('V1'), rms3('I1'), rms3('V2'), rms3('I2'));
    Rmag  = recover(abs(ph3('V1')), abs(ph3('I1')), abs(ph3('V2')), abs(ph3('I2')));
    Rpha  = abs(recover(ph3('V1'), ph3('I1'), ph3('V2'), ph3('I2')));

    fprintf('%-19s %6.1f %6.1f %6.1f  %6.1f %6.1f %6.1f  %6.1f %6.1f %6.1f\n', ...
            cases{i,1}, Rrms, Rmag, Rpha);
end

close_system(mdl, 0);
fprintf('\ntarget is %g %g %g in every block.\n', Rset);


function p = phasor(d, t, f)
%PHASOR  complex fundamental phasor per column (RMS magnitude).
w = 2*pi*f;
a = 2 * mean(d .* cos(w*t), 1);
b = 2 * mean(d .* sin(w*t), 1);
p = (a - 1j*b) / sqrt(2);
end
