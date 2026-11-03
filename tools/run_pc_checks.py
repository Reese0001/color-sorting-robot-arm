"""Run portable C and BSL unit tests on the PC. Never opens a hardware port."""
from pathlib import Path
import subprocess
import sys
from build_robot_sim import ROOT, BUILD, compiler, run_tests


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    executable = BUILD / 'test_protocols.exe'
    subprocess.run([compiler(), '-std=c99', '-Wall', '-Wextra', '-Werror',
                    '-Ifirmware/lib/k230_protocol', '-Ifirmware/lib/hiwonder_bus',
                    'tests/test_protocols.c', 'firmware/lib/k230_protocol/k230_protocol.c',
                    'firmware/lib/hiwonder_bus/hiwonder_bus.c', '-o', str(executable)],
                   cwd=ROOT, check=True)
    subprocess.run([str(executable)], cwd=ROOT, check=True)
    print(run_tests(), flush=True)
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                    '-s', 'tests', '-p', 'test_bsl_direct.py'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
