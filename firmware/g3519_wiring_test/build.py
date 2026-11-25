"""Build the G3519 bench diagnostic and check its main-flash Intel HEX image."""
import argparse
import os
from pathlib import Path
import struct
import subprocess

src = Path(__file__).resolve().parent
root = src.parents[1]
sdk = Path(os.getenv("MSPM0_SDK", "C:/TI/mspm0_sdk_2_10_00_04"))
cc = Path(os.getenv("TI_COMPILER", "D:/DevTools/ti/ccs2050/ccs/tools/compiler/ti-cgt-armllvm_4.0.4.LTS/bin/tiarmclang.exe"))
syscfg = os.getenv("SYSCONFIG_CLI", "C:/TI/sysconfig_1.26.2/sysconfig_cli.bat")


def run(gen, *args):
    # TI's Windows driver can resolve its runtime headers relative to the CWD.
    work = cc.parent.parent if args[0] == cc else gen
    subprocess.run([str(a) for a in args], cwd=work, check=True)


def validate(path):
    memory = {}
    base = 0
    records = path.read_text().splitlines()
    for line in records:
        data = bytes.fromhex(line[1:])
        assert line.startswith(":") and len(data) == data[0] + 5 and sum(data) % 256 == 0
        address, kind = int.from_bytes(data[1:3], "big"), data[3]
        if kind == 4:
            base = int.from_bytes(data[4:-1], "big") << 16
        elif kind == 2:
            base = int.from_bytes(data[4:-1], "big") << 4
        elif kind == 0:
            for i, b in enumerate(data[4:-1]):
                a = base + address + i
                assert a < 0x80000 and a not in memory, hex(a)
                memory[a] = b
        else:
            assert kind in (1, 3, 5)
    assert records[-1].upper() == ":00000001FF"
    stack, reset = struct.unpack("<II", bytes(memory[i] for i in range(8)))
    assert 0x20200000 < stack <= 0x20220000 and reset & 1 and (reset - 1) in memory
    print(f"Verified {len(memory)} flash bytes, SP={stack:#x}, reset={reset:#x}")


def main(servo24=False, bus_jog=False):
    if bus_jog:
        name, script = "bus_jog_test", "bus_jog.syscfg"
    elif servo24:
        name, script = "servo24_test", "servo24.syscfg"
    else:
        name, script = "wiring_test", "wiring.syscfg"
    gen = root / "build" / ("g3519_" + name)
    dest = root / "output/mspm0g3519" / (name + ".hex")
    config = src / script
    gen.mkdir(parents=True, exist_ok=True)
    run(gen, syscfg, "-s", sdk/".metadata/product.json", "--script", config,
        "-o", gen, "--compiler", "ticlang")
    opts = ["-mcpu=cortex-m0plus", "-mthumb", "-mfloat-abi=soft", "-Oz",
            "-D__MSPM0G3519__", "-D__USE_SYSCONFIG__", "-Wall", "-Wextra"]
    opts += ["-I"+str(p) for p in [gen, src, sdk/"source", root/"build/sdk_overlay",
                                    sdk/"source/third_party/CMSIS/Core/Include"]]
    startup = sdk/"source/ti/devices/msp/m0p/startup_system_files/ticlang/startup_mspm0g351x_ticlang.c"
    objs = []
    sources = [gen/"ti_msp_dl_config.c", startup, src/"oled.c"]
    if bus_jog:
        sources.append(src/"bus_jog.c")
    else:
        sources.extend([src/"main.c", src/"range.cpp", src/"pololu/VL53L0X.cpp"])
    if servo24:
        sources.append(src/"servo24_test.c")
    for f in sources:
        obj = gen/(f.stem + ".o")
        run(gen, cc, *opts, "-c", f, "-o", obj)
        objs.append(obj)
    run(gen, cc, *opts, "-o", gen/"wiring.out", *objs, "-Wl,-i"+str(gen), "-Wl,-ldevice_linker.cmd",
        "-Wl,-i"+str(sdk/"source"), "-Wl,-i"+str(cc.parent.parent/"lib"),
        "-Wl,-ldevice.cmd.genlibs", "-Wl,-llibc.a",
        "-Wl,--stack_size=4096", "-Wl,--rom_model", "-Wl,-m,"+str(gen/"wiring.map"))
    image = gen/"wiring.hex"
    run(gen, cc.with_name("tiarmobjcopy.exe"), "-O", "ihex", "wiring.out", image)
    validate(image)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image.read_bytes())
    print(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--servo24", action="store_true", help="build the A08 button-operated servo test")
    group.add_argument("--bus-jog", action="store_true", help="build the three-ID BusLinker battery test")
    options = parser.parse_args()
    main(options.servo24, options.bus_jog)
