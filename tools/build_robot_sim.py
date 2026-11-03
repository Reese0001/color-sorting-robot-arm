"""Build the desktop simulator from the firmware's portable C sources."""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'tools/build'
CORE = [ROOT / ('firmware/src/' + name) for name in
        ('robot_config.c', 'robot_workflow.c', 'robot_console.c')]
HEADERS = list((ROOT / 'firmware/include').glob('robot_*.h'))
BACKEND = ROOT / 'tools/robot_sim_backend.c'

def compiler():
    requested = os.environ.get('ROBOT_SIM_CC')
    candidates = [requested, shutil.which('gcc'),
                  r'C:\Program Files (x86)\Dev-Cpp\MinGW64\bin\gcc.exe']
    for path in candidates:
        if path and Path(path).is_file():
            return str(Path(path))
    raise RuntimeError('GCC not found. Set ROBOT_SIM_CC to the MinGW64 gcc.exe path.')

def run_compile(extra, sources, destination):
    BUILD.mkdir(parents=True, exist_ok=True)
    cmd = [compiler(), '-std=c99', '-Wall', '-Wextra', '-Werror', '-O2',
           '-I' + str(ROOT / 'firmware/include'), *extra,
           *map(str, sources), '-o', str(destination)]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                            errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)

def build_library():
    digest = hashlib.sha256()
    for path in [*CORE, *HEADERS, BACKEND, Path(__file__)]:
        digest.update(path.read_bytes())
    # Unique names allow an older simulator window to remain open during edits.
    output = BUILD / ('robot_sim_' + digest.hexdigest()[:12] + '.dll')
    if not output.exists():
        run_compile(['-shared', '-static-libgcc'], [*CORE, BACKEND], output)
    return output

def run_tests():
    output = BUILD / 'test_workflow.exe'
    run_compile([], [*CORE, ROOT / 'tests/test_workflow.c'], output)
    result = subprocess.run([str(output)], capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--test', action='store_true')
    args = p.parse_args()
    print(build_library())
    if args.test:
        print(run_tests())
