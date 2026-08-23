function setup_paths()
%SETUP_PATHS  Put scripts/ and model/ on the MATLAB path.
%
%   Run this once per MATLAB session before using anything else:
%
%       >> setup_paths
%       >> build_sweep_model          % rebuild the working model
%       >> run_pilot                  % 15 diagnostic runs
%       >> run_sweep(1,4)             % one slice of the full sweep
%
%   Needed because the model lives in model/ and the code in scripts/, and
%   Simulink can only load a model by name if its folder is on the path.

root = fileparts(mfilename('fullpath'));
addpath(fullfile(root, 'scripts'));
addpath(fullfile(root, 'model'));
fprintf('project root: %s\n', root);
fprintf('added scripts/ and model/ to the MATLAB path\n');
end
