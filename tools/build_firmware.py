"""Generate SysConfig, compile and link the real MSPM0G3507 firmware. No flashing."""
import argparse
import os
from pathlib import Path
import subprocess
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', default=os.getenv('MSPM0_SDK', 'C:/TI/mspm0_sdk_2_10_00_04'))
    parser.add_argument('--sysconfig', default=os.getenv('SYSCONFIG_CLI', 'C:/TI/sysconfig_1.26.2/sysconfig_cli.bat'))
    parser.add_argument('--compiler', default=os.getenv('TI_COMPILER', 'D:/DevTools/ti/ccs2050/ccs/tools/compiler/ti-cgt-armllvm_4.0.4.LTS/bin/tiarmclang.exe'))
    parser.add_argument('--repair-sdk', action='store_true', help='Fetch missing TI headers at pinned SDK 2.10 commit into build/sdk_overlay')
    args = parser.parse_args()
    sdk, compiler = Path(args.sdk), Path(args.compiler)
    output = ROOT / 'build/mspm0'
    output.mkdir(parents=True, exist_ok=True)

    overlay = ROOT / 'build/sdk_overlay'
    def run(command):
        print('RUN', subprocess.list2cmdline([str(x) for x in command]), flush=True)
        subprocess.run([str(x) for x in command], cwd=ROOT, check=True)

    run([args.sysconfig, '-s', sdk / '.metadata/product.json', '--script',
         ROOT / 'firmware/mspm0/robot.syscfg', '-o', output, '--compiler', 'ticlang'])
    common = ['-march=thumbv6m', '-mcpu=cortex-m0plus', '-mfloat-abi=soft', '-mthumb',
              '-O2', '-g', '-Wall', '-Wextra', '-D__MSPM0G3507__', '-D__USE_SYSCONFIG__',
              '-I' + str(ROOT / 'firmware/mspm0'), '-I' + str(output),
              '-I' + str(overlay),
              '-I' + str(sdk / 'source'), '-I' + str(sdk / 'source/third_party/CMSIS/Core/Include')]
    sources = [ROOT / 'firmware/mspm0/main.c', ROOT / 'firmware/mspm0/robot.c',
               output / 'ti_msp_dl_config.c',
               sdk / 'source/ti/devices/msp/m0p/startup_system_files/ticlang/startup_mspm0g350x_ticlang.c']
    objects = []
    for source in sources:
        obj = output / (source.stem + '.o')
        command = [str(x) for x in [compiler, *common, '-c', source, '-o', obj]]
        for attempt in range(50):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            if result.returncode == 0:
                print('COMPILED', source.name)
                if result.stderr: print(result.stderr)
                break
            missing = re.search(r"fatal error: '(ti/[a-zA-Z0-9_./]+\.h)' file not found", result.stderr)
            if not args.repair_sdk or not missing:
                raise RuntimeError(result.stderr)
            rel = missing.group(1)
            if '..' in Path(rel).parts:
                raise RuntimeError('Unexpected include path')
            dest = overlay / rel
            if dest.exists(): raise RuntimeError(result.stderr)
            dest.parent.mkdir(parents=True, exist_ok=True)
            url = 'https://raw.githubusercontent.com/TexasInstruments/mspm0-sdk/e249e2bd63bcc912176a30a45a6a5dcea951168b/source/' + rel
            run(['curl.exe', '--fail', '--location', '--silent', '--show-error', url, '-o', dest])
        else:
            raise RuntimeError('Too many missing headers')
        objects.append(obj)
    target = output / 'robot1.out'
    run([compiler, *common, '-o', target, *objects,
         '-Wl,-i' + str(output), '-Wl,-i' + str(sdk / 'source'),
         '-Wl,-i' + str(compiler.parent.parent / 'lib'),
         '-Wl,-l' + str(output / 'device_linker.cmd'), '-Wl,-ldevice.cmd.genlibs',
         '-Wl,-llibc.a', '-Wl,--rom_model', '-Wl,-m' + str(output / 'robot1.map')])
    run([compiler.parent / 'tiarmobjcopy.exe', '-O', 'ihex', target, output / 'robot1.hex'])
    print('BUILT', target)


if __name__ == '__main__':
    main()
