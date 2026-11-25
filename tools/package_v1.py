"""Create a curated delivery ZIP, excluding caches and legacy STM32 code."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json

root = Path(__file__).resolve().parents[1]
out = root / 'dist'
out.mkdir(exist_ok=True)
readme = root / 'README_G3507_V1.md'
if not readme.is_file():  # The standalone V1 archive uses README.md.
    readme = root / 'README.md'
files = [readme, root / 'LICENSE']
files += [p for p in (root / 'firmware/mspm0').iterdir() if p.suffix in ('.c', '.h', '.syscfg')]
for folder, names in {
    'vision/k230': ('README.md', 'three_color_blocks.py', 'robot_link.py', 'coordinate_map.py'),
    'tools': ('build_firmware.py', 'console.py', 'create_calibration_map.py', 'package_v1.py', 'test_firmware.py'),
    'tests': ('robot_core_harness.c', 'test_k230_vision.py', 'test_robot_link.py'),
}.items():
    files.extend(root / folder / name for name in names)
files += [root / 'docs' / name for name in
          ('从零开始.md', 'wiring_v1.md', 'testing_v1.md', 'protocol.md', 'validation_v1.md')]
files += [root / 'build/mspm0' / name for name in ('robot1.out', 'robot1.hex', 'robot1.map')]
manifest = {}
with ZipFile(out / 'robot1_v1.zip', 'w', ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        data = path.read_bytes()
        relative = 'README.md' if path == readme else path.relative_to(root).as_posix()
        archive.writestr('robot1_v1/' + relative, data)
        manifest[relative] = hashlib.sha256(data).hexdigest()
    archive.writestr('robot1_v1/manifest_sha256.json', json.dumps(manifest, indent=2))
print(out / 'robot1_v1.zip')
