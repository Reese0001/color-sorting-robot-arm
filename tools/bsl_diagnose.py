"""Read-only MAIN diagnostics after the already accepted default BSL password.

Never erase, program, change protection, or start the application.
"""
import argparse
import json
import struct
import time
from bsl_direct import BSL, CoreError, DotNetSerial, ROOT, SIZE, checked_image, crc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='COM8')
    parser.add_argument('--wait', type=int, default=240)
    args = parser.parse_args()
    image, _ = checked_image()
    folder = ROOT / 'tools/bsl_direct_logs'
    auth = folder / 'auth_state.json'
    if json.loads(auth.read_text())['state'] not in ('unlocked', 'verified'):
        raise RuntimeError('No confirmed successful password history; stopped')
    report = {'port': args.port, 'read_only': True, 'sectors': []}
    tag = time.strftime('%Y%m%d_%H%M%S_diagnose')
    port = DotNetSerial(args.port)
    try:
        port.open()
        print('READY_READ_ONLY_BSL: waiting for connection', flush=True)
        bsl = BSL(port)
        bsl.wait_connection(args.wait)
        report['device_info'] = bsl.command(b'\x19', 0x31, 25).hex()
        auth.write_text(json.dumps({'state': 'attempt_started'}))
        bsl.command(b'\x21' + b'\xff' * 32, 0x3B, 2)
        auth.write_text(json.dumps({'state': 'unlocked'}))
        print('UNLOCK_OK; no writes or erases', flush=True)
        try:
            first = bsl.command(b'\x29' + struct.pack('<II', 0, 128), 0x30, 129)[1:]
        except CoreError as exc:
            if exc.code != 9:
                raise
            report['readback'] = 'disabled by device policy; left unchanged'
            print('READBACK_DISABLED; collecting sector CRCs', flush=True)
        else:
            data = bytearray(first)
            for address in range(128, SIZE, 128):
                data.extend(bsl.command(b'\x29' + struct.pack('<II', address, 128), 0x30, 129)[1:])
            (folder / (tag + '.bin')).write_bytes(data)
            report['readback_matches'] = data == image
            report['first_differences'] = [{'address': i, 'expected': a, 'actual': b}
                for i, (a, b) in enumerate(zip(image, data)) if a != b][:32]
            print('READBACK_MATCHES=' + str(data == image), flush=True)
        for address, count in [(0, SIZE)] + [(x, 1024) for x in range(0, SIZE, 1024)] + [(0, SIZE)]:
            response = bsl.command(b'\x26' + struct.pack('<II', address, count), 0x32, 5)
            actual, expected = int.from_bytes(response[1:], 'little'), crc(image[address:address + count])
            entry = {'address': address, 'length': count, 'actual': f'{actual:08X}', 'expected_wire_crc': f'{expected:08X}'}
            report['sectors'].append(entry)
            print(json.dumps(entry), flush=True)
    except Exception as exc:
        report['error'] = str(exc)
        print('FAILED: ' + str(exc), flush=True)
    finally:
        port.close()
        (folder / (tag + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 1 if 'error' in report else 0


if __name__ == '__main__':
    raise SystemExit(main())
