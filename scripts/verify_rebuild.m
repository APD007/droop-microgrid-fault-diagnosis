% Rebuild with scopes commented out, then confirm the numbers are unchanged.
% Commenting visualisation blocks must not move the data by even a digit.

root = project_root();
mdl  = 'Droop_control_conditioning_claude';
load_system(fullfile(root,'model',[mdl '.slx']));
H = [1 1 1 1 1 1];

in = Simulink.SimulationInput(mdl);
in = in.setVariable('R_A_a',32); in = in.setVariable('R_A_b',32);
in = in.setVariable('R_A_c',32); in = in.setVariable('F1',H);
in = in.setVariable('F2',H);
sim(in);                                   % warm the target
t0 = tic; out = sim(in); el = toc(t0);
f  = extract_features(out, 4);
close_system(mdl,0);

P = readtable(fullfile(root,'pilot','pilot_results.csv'),'VariableNamingRule','preserve');
p = P(1, :);   % pilot case 1: healthy, balanced 32

fprintf('\n=== regression check: healthy, balanced 32 ohm ===\n');
fprintf('%-10s %14s %14s %12s\n', 'feature', 'pilot (scopes)', 'now (no scopes)', 'diff');
names = {'V1_a','V1_b','V1_c','I1_a','I1_b','I1_c', ...
         'V2_a','V2_b','V2_c','I2_a','I2_b','I2_c','f1'};
worst = 0;
for k = 1:numel(names)
    a = p.(names{k});  b = f.(names{k});  d = abs(a-b);
    worst = max(worst, d/max(abs(a),eps));
    fprintf('%-10s %14.6f %14.6f %12.2e\n', names{k}, a, b, d);
end
fprintf('\nworst relative difference: %.3e\n', worst);
if worst < 1e-9
    fprintf('IDENTICAL - the speedup is free.\n');
else
    fprintf('*** numbers moved - investigate before sweeping ***\n');
end
fprintf('run time now: %.1f s\n', el);
