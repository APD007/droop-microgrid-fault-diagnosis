function T = features_from_logs(source, outCsv, ncyc)
%FEATURES_FROM_LOGS  Turn Simulink runs into a CSV that predict.py can read.
%
%   This is the bridge for testing the model on new data. It takes logged
%   waveforms and produces the 42 measured columns the model requires.
%
%   T = FEATURES_FROM_LOGS(source, outCsv)
%
%   source may be any of:
%     - a Simulink.SimulationOutput            (one run)
%     - an array of Simulink.SimulationOutput  (several runs)
%     - a path to a .mat file containing either of the above saved as 'out'
%
%   The logged signals must be named V1, I1, V2, I2 (each N-by-3, phases a b c)
%   and f1, f2. A model built by build_sweep_model.m already logs exactly
%   these, so the simplest way to generate test data is:
%
%       setup_paths
%       in = Simulink.SimulationInput('Droop_control_conditioning_claude');
%       in = in.setVariable('R_A_a', 40);       % any values, on or off lattice
%       in = in.setVariable('R_A_b', 40);
%       in = in.setVariable('R_A_c', 72);
%       in = in.setVariable('F1', [1 1 0 1 1 1]);   % DG1 pulse 3 open
%       in = in.setVariable('F2', [1 1 1 1 1 1]);
%       out = sim(in);
%       features_from_logs(out, 'my_test.csv');
%
%   then, from the shell:
%
%       python scripts/predict.py my_test.csv
%
%   ncyc defaults to 4 and must match what the model was trained with. Do not
%   change it without retraining - the averaging window is part of the feature
%   definition, not a free parameter.

if nargin < 3 || isempty(ncyc), ncyc = 4; end
if nargin < 2 || isempty(outCsv), outCsv = 'features.csv'; end

% ---- normalise the input to an array of SimulationOutput ---------------
if (ischar(source) || isstring(source))
    S = load(char(source));
    fn = fieldnames(S);
    if isfield(S, 'out'), source = S.out; else, source = S.(fn{1}); end
end
if ~isa(source, 'Simulink.SimulationOutput')
    error('features_from_logs:badInput', ...
          ['source must be a Simulink.SimulationOutput, an array of them, ' ...
           'or a .mat file containing one']);
end

n = numel(source);
fprintf('extracting features from %d run(s), %d-cycle window\n', n, ncyc);

rows = cell(n, 1);
for k = 1:n
    f = extract_features(source(k), ncyc);     % the same function the sweep used
    rows{k} = struct2table(f);
end
T = vertcat(rows{:});

% ---- keep only the 42 the model needs, in a stable order --------------
p = {'a','b','c'};
want = {};
for base = {'V1','I1','V2','I2', 'I1mean','I2mean', ...
            'V1f','I1f','V2f','I2f', 'V1ang','I1ang','V2ang','I2ang'}
    for j = 1:3, want{end+1} = [base{1} '_' p{j}]; end %#ok<AGROW>
end
missing = setdiff(want, T.Properties.VariableNames);
if ~isempty(missing)
    error('features_from_logs:missing', ...
          'extract_features did not produce: %s', strjoin(missing, ', '));
end

% diagnostics are carried through; they are ignored by predict.py but are
% worth having alongside the predictions
keep = [want, intersect({'f1','f2','P1','P2','Q1','Q2'}, ...
                        T.Properties.VariableNames, 'stable')];
T = T(:, keep);

writetable(T, outCsv);
fprintf('wrote %s  (%d rows x %d columns)\n', outCsv, height(T), width(T));
fprintf('now run:  python scripts/predict.py %s\n', outCsv);
end
