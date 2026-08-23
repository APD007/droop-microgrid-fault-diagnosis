function r = fundamental_rms(d, t, f)
%FUNDAMENTAL_RMS  RMS of the fundamental component only, per column.
%
%   r = FUNDAMENTAL_RMS(d, t, f) where d is N-by-M samples, t is the matching
%   time vector, and f is the fundamental frequency in Hz.
%
%   Why this exists. True RMS includes every harmonic. Under an open-switch
%   fault the current waveform is badly distorted, so its true RMS no longer
%   satisfies Ohm's law and the load resistance cannot be recovered from it.
%
%   But the load is a pure resistor, and a resistor is linear: it responds to
%   each frequency independently. So at the fundamental,
%
%       I_fundamental = V_fundamental / R      exactly
%
%   regardless of how distorted the total waveform is - all the distortion
%   lives in the other harmonics. Projecting onto the fundamental recovers
%   Ohm's law exactly, fault or no fault.
%
%   Method: project onto cos and sin at f over the window (a Fourier
%   coefficient at the fundamental). Exact when the window spans a whole
%   number of periods, which is how extract_features chooses it.

w = 2*pi*f;
c = cos(w*t);
s = sin(w*t);

a = 2 * mean(d .* c, 1);        % in-phase amplitude, per column
b = 2 * mean(d .* s, 1);        % quadrature amplitude

r = sqrt(a.^2 + b.^2) / sqrt(2);   % peak amplitude -> RMS
end
