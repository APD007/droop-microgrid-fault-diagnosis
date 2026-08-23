function build_sweep_model(keepScopes)
%BUILD_SWEEP_MODEL  Create the sweep-ready copy of the delivered model.
%
%   build_sweep_model()       scopes commented out - fast, for sweeping
%   build_sweep_model(true)   scopes left live - slower, for looking at
%
%   Reads  Droop_control_conditioning_untouched.slx  (pristine - NEVER modified)
%   Writes Droop_control_conditioning_claude.slx     (working copy)
%
%   Run this once. It is idempotent: it always starts from a fresh copy of
%   the untouched model, so re-running it DISCARDS any hand edits made to
%   the _claude copy. Edit this script, not the model, to change behaviour.
%
%   The five changes, and why each is needed:
%
%   [1] RMS / Display5 / Scope5 are commented out (not deleted). That chain
%       is a dead end - the RMS block's input is unconnected and it comes
%       from DSP System Toolbox, which is not installed on this machine, so
%       its library link is unresolved and the model will not compile with
%       it live. Commenting is reversible; deleting is not.
%
%   [2] InitFcn is rewritten with ~exist guards. InitFcn re-runs on every
%       simulation start, so without guards it overwrites anything pushed in
%       by Simulink.SimulationInput.setVariable, and every run in the sweep
%       would silently use the default load and no fault.
%
%   [3] The nine load resistances were hardcoded literals typed into block
%       dialogs, which setVariable cannot reach. They become named variables.
%
%   [4] One element-wise Product plus a Constant per inverter applies the
%       6-element pulse mask F1 / F2. Forcing a gate pulse to zero holds that
%       IGBT permanently off - the standard open-switch fault model. No block
%       is deleted or disconnected.
%
%   [5] Signal logging is switched on for the measurement signals. This is a
%       property on an output port, not a new block.

if nargin < 1, keepScopes = false; end

root    = project_root();
src     = 'Droop_control_conditioning_untouched';
dst     = 'Droop_control_conditioning_claude';
srcFile = fullfile(root, 'model', [src '.slx']);
dstFile = fullfile(root, 'model', [dst '.slx']);

if bdIsLoaded(dst), close_system(dst, 0); end
copyfile(srcFile, dstFile, 'f');
load_system(dstFile);
fprintf('=== building %s.slx from %s.slx ===\n\n', dst, src);

%% [1] neutralise the dangling DSP RMS chain ----------------------------
for b = {'RMS','Display5','Scope5'}
    set_param([dst '/' b{1}], 'Commented', 'on');
end
fprintf('[1] commented out RMS / Display5 / Scope5 (reversible, not deleted)\n');

%% [1b] scopes and displays --------------------------------------------
% Pure visualisation - they cannot affect the computed result, but each one
% still processes all 400,001 samples of every run. Measured cost: 1.94x on
% total runtime, i.e. they are about half the sweep. Commented, not deleted,
% and the untouched model still has all of them for looking at.
if keepScopes
    fprintf('[1b] scopes/displays left LIVE (keepScopes=true) - ~2x slower\n');
else
    vis = [ find_system(dst,'LookUnderMasks','all','BlockType','Scope')
            find_system(dst,'LookUnderMasks','all','BlockType','Display') ];
    n = 0;
    for k = 1:numel(vis)
        if ~strcmp(get_param(vis{k},'Commented'),'on')
            set_param(vis{k}, 'Commented', 'on');  n = n + 1;
        end
    end
    fprintf('[1b] commented out %d Scope/Display blocks (1.94x speedup)\n', n);
end

%% [2] guarded InitFcn --------------------------------------------------
q = @(s) ['''' s ''''];   % helper so the quoting below stays readable
g = @(name, val, cmt) sprintf('if ~exist(%s,''var''), %-6s = %-10s end   %% %s', ...
                              q(name), name, [val ';'], cmt);
L = {
'%% ===== Parameters =====================================================';
'%% Every primary parameter is wrapped in ~exist so that a value pushed in';
'%% by Simulink.SimulationInput.setVariable survives this callback. Without';
'%% the guard, InitFcn re-runs at every simulation start and silently';
'%% overwrites the swept value.';
'';
'%% ---- Droop control ----';
g('m1',   '0.5e-5',  'f-P droop gain');
g('n1',   '5e-3',    'Q-V droop gain');
g('fn',   '50',      'nominal frequency, Hz');
g('Vn',   '325',     'nominal voltage, peak');
g('wc',   '2*pi*5',  'droop low-pass cutoff');
'';
'%% ---- Voltage controller ----';
g('kpv',  '1',       'proportional gain');
g('kiv',  '189',     'integral gain');
g('F',    '0.75',    'feedforward gain');
g('Ilim1','40',      'upper limit');
g('Ilim2','-40',     'lower limit');
'';
'%% ---- Current controller ----';
g('kpi',  '10.47*2', 'proportional gain');
g('kii',  '4188.8*4','integral gain');
g('Vlim1','500',     'upper limit');
g('Vlim2','500',     'lower limit');
'';
'%% ---- System parameters ----';
g('Lf',   '1.6e-3',  'filter inductance');
g('Cf',   '50e-6',   'filter capacitance');
g('Rc',   '0.03',    'coupling resistance');
g('Lc',   '0.35e-3', 'coupling inductance');
g('fs',   '10e3',    'switching frequency');
g('Ts',   '10e-7',   'solver step - FixedStep follows this');
g('Vin',  '1000',    'DC link voltage');
g('ts',   '0.04',    'black start time');
'Tsample = 20*Ts;                        % derived from Ts, never guarded';
'';
'%% ---- Line parameters ----';
g('R1',   '0.23',    'line resistance');
g('L1',   '3.1e-4',  'line inductance');
'';
'%% ---- Load bank resistances, per phase, ohm ----';
'%% Bank A: DG1 bus, always connected        (delivered 32 / 32 / 32)';
'%% Bank B: DG1 bus, behind breaker at t=1s  (delivered 160 / 160 / 160)';
'%% Bank C: DG2 bus, always connected        (delivered 160 / 160 / 160)';
'%% Only bank A is swept; B and C stay at their delivered values.';
g('R_A_a','32',      'bank A phase a  <-- swept');
g('R_A_b','32',      'bank A phase b  <-- swept');
g('R_A_c','32',      'bank A phase c  <-- swept');
g('R_B_a','160',     'bank B phase a');
g('R_B_b','160',     'bank B phase b');
g('R_B_c','160',     'bank B phase c');
g('R_C_a','160',     'bank C phase a');
g('R_C_b','160',     'bank C phase b');
g('R_C_c','160',     'bank C phase c');
'';
'%% ---- PWM pulse masks: 1 = pulse connected, 0 = switch held open ----';
'%% Pulse-to-IGBT mapping is verified empirically by run_pilot.m; see the';
'%% mapping note written there before trusting any per-pulse label.';
g('F1',   '[1 1 1 1 1 1]', 'inverter 1  <-- swept');
g('F2',   '[1 1 1 1 1 1]', 'inverter 2  <-- swept');
};
set_param(dst, 'InitFcn', strjoin(L, newline));
fprintf('[2] InitFcn rewritten with ~exist guards (%d lines)\n', numel(L));

%% [3] load resistances -> named variables ------------------------------
map = { 'Series RLC Branch',  'R_A_a'
        'Series RLC Branch1', 'R_A_b'
        'Series RLC Branch2', 'R_A_c'
        'Series RLC Branch3', 'R_B_a'
        'Series RLC Branch4', 'R_B_b'
        'Series RLC Branch5', 'R_B_c'
        'Series RLC Branch6', 'R_C_a'
        'Series RLC Branch7', 'R_C_b'
        'Series RLC Branch8', 'R_C_c' };
fprintf('[3] load resistances -> variables:\n');
for k = 1:size(map,1)
    blk = [dst '/' map{k,1}];
    was = get_param(blk, 'Resistance');
    set_param(blk, 'Resistance', map{k,2});
    fprintf('      %-20s  %-5s -> %s\n', map{k,1}, was, map{k,2});
end

%% [4] pulse mask injection ---------------------------------------------
% Existing chain inside each Droop Control subsystem:
%   PWM Generator -> Unit Delay -> Product3 (x Step3, the black start)
%                 -> Demux(6) -> Mux(6) -> Goto P -> Universal Bridge
% The mask is spliced between Product3 and Demux, so it multiplies the
% 6-element pulse vector after the black-start gate.
fprintf('[4] pulse mask injection:\n');
dgs = {'Droop Control 1','F1'; 'Droop Control 2','F2'};
for k = 1:size(dgs,1)
    sub  = [dst '/' dgs{k,1}];
    posP = get_param([sub '/Product3'], 'Position');
    posD = get_param([sub '/Demux'],    'Position');

    delete_line(sub, 'Product3/1', 'Demux/1');

    add_block('simulink/Math Operations/Product', [sub '/PulseMask']);
    set_param([sub '/PulseMask'], 'Inputs','2', ...
        'Multiplication','Element-wise(.*)', ...
        'Position', [posD(1)-75, posP(2)-5, posD(1)-45, posP(2)+25]);

    add_block('simulink/Sources/Constant', [sub '/FaultMaskConst']);
    set_param([sub '/FaultMaskConst'], 'Value', dgs{k,2}, ...
        'Position', [posD(1)-190, posP(2)-75, posD(1)-110, posP(2)-45]);

    add_line(sub, 'Product3/1',       'PulseMask/1', 'autorouting','on');
    add_line(sub, 'FaultMaskConst/1', 'PulseMask/2', 'autorouting','on');
    add_line(sub, 'PulseMask/1',      'Demux/1',     'autorouting','on');

    fprintf('      %s: Product3 -> [PulseMask .* %s] -> Demux\n', dgs{k,1}, dgs{k,2});
end

%% [5] signal logging ----------------------------------------------------
% Dataset columns come from the subsystem outports:
%   Outport 1 = Vabc  (phase-to-ground at the filter-capacitor bus)
%   Outport 2 = IabcL (current into the coupling impedance)
% f1/f2 size the RMS window exactly; P/Q are diagnostics only.
fprintf('[5] signal logging (decimation 10 -> 100 kHz):\n');
ports = {'Droop Control 1', 1, 'V1'; 'Droop Control 1', 2, 'I1'
         'Droop Control 2', 1, 'V2'; 'Droop Control 2', 2, 'I2'};
for k = 1:size(ports,1)
    ph = get_param([dst '/' ports{k,1}], 'PortHandles');
    tag_log(ph.Outport(ports{k,2}), ports{k,3});
    fprintf('      %-3s <- %s outport %d\n', ports{k,3}, ports{k,1}, ports{k,2});
end
% root-level From blocks carrying the global droop tags
froms = {'From','f1'; 'From6','f2'; 'From3','P1'; 'From2','P2'
         'From19','Q1'; 'From1','Q2'};
for k = 1:size(froms,1)
    ph = get_param([dst '/' froms{k,1}], 'PortHandles');
    tag_log(ph.Outport(1), froms{k,2});
end
fprintf('      f1 f2 P1 P2 Q1 Q2 <- root From blocks (diagnostics)\n');

%% [6] simulation configuration -----------------------------------------
set_param(dst, 'StopTime','0.4', 'SimulationMode','accelerator', ...
               'SignalLogging','on', 'SignalLoggingName','logsout', ...
               'SaveOutput','off', 'SaveState','off');
fprintf('[6] StopTime=0.4 s, accelerator, logsout on, SaveOutput off\n');

%% [7] verify and save ---------------------------------------------------
fprintf('\n--- compiling ---\n');
set_param(dst, 'SimulationCommand', 'update');
fprintf('COMPILE: ok\n');
save_system(dst, dstFile);
close_system(dst, 0);
fprintf('\n=== saved model/%s.slx ===\n', dst);
end


function tag_log(port, name)
%TAG_LOG  Mark one output port for signal logging under a fixed name.
set_param(port, 'DataLogging','on', ...
                'DataLoggingNameMode','Custom', ...
                'DataLoggingName', name, ...
                'DataLoggingDecimateData','on', ...
                'DataLoggingDecimation','10');
end
