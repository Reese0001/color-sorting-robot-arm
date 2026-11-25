"""Compile and run the actual C controller against simulated hardware."""
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'build/host'
out.mkdir(parents=True, exist_ok=True)
target = out / 'robot_core_test.exe'
subprocess.run([sys.executable, '-m', 'ziglang', 'cc', '-std=c11', '-Wall', '-Wextra',
                '-Werror', '-I' + str(ROOT / 'firmware/mspm0'),
                str(ROOT / 'firmware/mspm0/robot.c'), str(ROOT / 'tests/robot_core_harness.c'),
                '-o', str(target)], check=True, cwd=ROOT)
subprocess.run([str(target)], check=True, cwd=ROOT)
