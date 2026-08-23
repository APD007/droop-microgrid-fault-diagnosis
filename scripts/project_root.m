function r = project_root()
%PROJECT_ROOT  Absolute path to the project folder, from anywhere.
%
%   Every script resolves its files through this rather than relying on the
%   current directory, so they work whether you run them from the project
%   root, from scripts/, or from a MATLAB session started somewhere else.
r = fileparts(fileparts(mfilename('fullpath')));
end
