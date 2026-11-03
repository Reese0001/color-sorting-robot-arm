"""Project-specific BSL uploader, based on TI SLAU887A (not a TI supplied tool).

Only the reviewed 16KiB MAIN image is allowed. No factory/mass erase, NONMAIN
writes, baud changes or password retries. Default operation is a read-only probe.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import struct
import subprocess
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
SIZE = 0x4000


class DotNetSerial:
    """Use the proven local .NET port implementation, not CH340/pySerial DCB setup."""
    def __init__(self, name):
        self.process = subprocess.Popen(
            ['pwsh.exe', '-NoLogo', '-NoProfile', '-File',
             str(ROOT / 'tools/serial_bridge.ps1'), '-Port', name, '-Baud', '9600'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)

    def rpc(self, op, **fields):
        self.process.stdin.write(json.dumps({'op': op, **fields}) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise IOError('Serial bridge ended: ' + self.process.stderr.read())
        result = json.loads(line)
        if not result['ok']:
            raise IOError(result['error'])
        return result.get('value')

    def open(self): self.rpc('open')
    def write(self, data): return self.rpc('write', data=base64.b64encode(data).decode('ascii'))
    def read(self, count): return base64.b64decode(self.rpc('read', count=count))
    def reset_input_buffer(self): self.rpc('reset')
    def flush(self): pass  # .NET SerialPort.Write completes its bounded write operation.
    def close(self):
        try:
            if self.process.poll() is None:
                self.rpc('close')
                self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None: self.process.terminate()


def crc(data):
    return zlib.crc32(data) ^ 0xFFFFFFFF


def packet(body):
    return b'\x80' + struct.pack('<H', len(body)) + body + struct.pack('<I', crc(body))


def validate_request(body):
    if not body:
        raise ValueError('Empty command')
    cmd = body[0]
    if cmd in (0x12, 0x19, 0x40) and len(body) == 1:
        return
    if cmd == 0x21 and body[1:] == b'\xff' * 32:
        return
    if cmd == 0x23 and body[1:] == struct.pack('<II', 0, SIZE - 1):
        return
    if cmd in (0x26, 0x29) and len(body) == 9:
        addr, count = struct.unpack('<II', body[1:])
        if addr + count <= SIZE and addr % 4 == 0:
            if cmd == 0x26 and 1024 <= count <= SIZE and count % 4 == 0:
                return
            if cmd == 0x29 and 1 <= count <= 512:
                return
    if cmd == 0x20 and len(body) >= 13:
        addr = struct.unpack('<I', body[1:5])[0]
        count = len(body) - 5
        if addr % 8 == 0 and count % 8 == 0 and count <= 128 and addr + count <= SIZE:
            return
    raise ValueError('Command outside reviewed MAIN-only operation set')


def checked_image():
    from hex_image import check_hex
    path = ROOT / 'firmware/keil/Objects/robot_mspm0.hex'
    expected = json.loads((ROOT / 'tools/uniflash/config.json').read_text())['firmware_sha256']
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('HEX changed; review firmware before updating the approved hash')
    report = check_hex(path)
    if report['first'] != '0x0' or int(report['last'], 16) >= SIZE:
        raise ValueError('Image outside first 16KiB of MAIN')
    output = bytearray(b'\xff' * SIZE)
    base = 0
    for line in path.read_text().splitlines():
        data = bytes.fromhex(line[1:])
        count, addr, kind = data[0], int.from_bytes(data[1:3], 'big'), data[3]
        body = data[4:4 + count]
        if kind == 0:
            output[base + addr:base + addr + count] = body
        elif kind == 2:
            base = int.from_bytes(body, 'big') << 4
        elif kind == 4:
            base = int.from_bytes(body, 'big') << 16
    config = (ROOT / 'firmware/include/app_config.h').read_text()
    if '#define MOTION_OUTPUT_ENABLE 0' not in config or '#define BUS_PROTOCOL_CONFIRMED 0' not in config:
        raise ValueError('Bench defaults changed')
    return bytes(output), report


class CoreError(ValueError):
    def __init__(self, payload):
        self.code = payload[1] if len(payload) == 2 else None
        super().__init__('BSL core error ' + payload.hex())


class BSL:
    def __init__(self, port):
        self.port = port

    def exact(self, length, seconds=4):
        result = bytearray()
        end = time.monotonic() + seconds
        while len(result) < length and time.monotonic() < end:
            result.extend(self.port.read(length - len(result)))
        if len(result) != length:
            raise TimeoutError(f'Incomplete BSL reply: {len(result)}/{length} bytes')
        return bytes(result)

    def command(self, body, reply_type=None, reply_size=None):
        validate_request(body)
        data = packet(body)
        if self.port.write(data) != len(data):
            raise IOError('Incomplete serial write; no automatic retry')
        self.port.flush()
        ack = self.exact(1)
        if ack != b'\x00':
            raise ValueError(f'BSL peripheral error {ack.hex()} for command {body[0]:02X}')
        if reply_type is None:
            return b''
        header = self.exact(3)
        length = int.from_bytes(header[1:], 'little')
        if header[0] != 8 or not 1 <= length <= 1024:
            raise ValueError('Invalid BSL response header/length')
        payload, checksum = self.exact(length), self.exact(4)
        if crc(payload) != int.from_bytes(checksum, 'little'):
            raise ValueError('BSL response CRC mismatch')
        if payload[0] == 0x3B and payload != b'\x3b\x00':
            raise CoreError(payload)
        if payload[0] != reply_type or (reply_size is not None and len(payload) != reply_size):
            raise ValueError('Unexpected BSL core response: ' + payload.hex())
        return payload

    def wait_connection(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.port.reset_input_buffer()
            self.port.write(packet(b'\x12'))
            self.port.flush()
            if self.port.read(1) == b'\x00':
                # In an already selected UART session, ROM treats 0x12 as a
                # core command and replies UNKNOWN_COMMAND after its ACK.
                # Consume that validated response before requesting device info.
                first = self.port.read(1)
                if first:
                    header = first + self.exact(2)
                    if header != b'\x08\x02\x00':
                        raise ValueError('Unexpected response after connection ACK: ' + header.hex())
                    payload, checksum = self.exact(2), self.exact(4)
                    if payload != b'\x3b\x06' or crc(payload) != int.from_bytes(checksum, 'little'):
                        raise ValueError('Invalid existing-session connection response')
                return
            time.sleep(0.15)
        raise TimeoutError('No BSL ACK. No password or erase command sent.')


def unlock(bsl, auth_record):
    # Persistent fail-closed state: never repeat an uncertain or rejected password.
    if auth_record.exists() and json.loads(auth_record.read_text())['state'] not in ('unlocked', 'verified'):
        raise RuntimeError('Previous unlock was uncertain/rejected; inspect it before any new attempt')
    auth_record.write_text(json.dumps({'state': 'attempt_started'}))
    bsl.command(b'\x21' + b'\xff' * 32, 0x3B, 2)
    auth_record.write_text(json.dumps({'state': 'unlocked'}))


def verify_image(bsl, image, auth_record, log):
    response = bsl.command(b'\x26' + struct.pack('<II', 0, SIZE), 0x32, 5)
    actual, expected = int.from_bytes(response[1:], 'little'), crc(image)
    if actual != expected:
        raise ValueError(f'MAIN verification failed: device={actual:08X}, expected={expected:08X}')
    auth_record.write_text(json.dumps({'state': 'verified', 'crc32': f'{actual:08X}'}))
    log(f'MAIN_CRC_VERIFIED: {SIZE} bytes, CRC={actual:08X}')
    return actual


def program_image(bsl, image, auth_record, log):
    unlock(bsl, auth_record)
    log('UNLOCK_OK; erasing MAIN 0x00000000..0x00003FFF only')
    bsl.command(b'\x23' + struct.pack('<II', 0, SIZE - 1), 0x3B, 2)
    log('MAIN_RANGE_ERASE_OK')
    for address in range(0, SIZE, 128):
        bsl.command(b'\x20' + struct.pack('<I', address) + image[address:address + 128], 0x3B, 2)
        if (address + 128) % 2048 == 0:
            log(f'PROGRAM {address + 128}/{SIZE}')
    actual = verify_image(bsl, image, auth_record, log)
    log(f'MAIN_PROGRAM_AND_CRC_VERIFIED: {SIZE} bytes, CRC={actual:08X}')
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='COM8')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--program', action='store_true')
    mode.add_argument('--verify-only', action='store_true', help='Verify existing MAIN, then start it; no erase/program')
    parser.add_argument('--wait', type=int, default=180)
    parser.add_argument('--transport', choices=['dotnet', 'pyserial'], default='dotnet')
    args = parser.parse_args()
    image, image_report = checked_image()  # Validate before opening any hardware.
    logs = ROOT / 'tools/bsl_direct_logs'
    logs.mkdir(exist_ok=True)
    tag = time.strftime('%Y%m%d_%H%M%S')
    report = {'port': args.port, 'transport': args.transport, 'program_requested': args.program, 'image': image_report,
              'verify_only_requested': args.verify_only,
              'verified': False, 'application_started': False, 'main_erased': False,
              'confirmed_written_bytes': 0}
    with (logs / f'{tag}.txt').open('w', encoding='utf-8') as transcript:
        def log(message):
            if message == 'MAIN_RANGE_ERASE_OK': report['main_erased'] = True
            if message.startswith('PROGRAM '):
                report['confirmed_written_bytes'] = int(message.split()[1].split('/')[0])
            print(message, flush=True)
            transcript.write(message + '\n')
            transcript.flush()
        if args.transport == 'pyserial':
            import serial
            port = serial.Serial(port=None, baudrate=9600, timeout=0.2, write_timeout=3)
            port.port, port.dtr, port.rts = args.port, False, False
        else:
            port = DotNetSerial(args.port)
        try:
            port.open()
            log('READY_AUTO_BSL: hold BSL, tap/release RST, wait 1s, release BSL. No Enter needed.')
            bsl = BSL(port)
            bsl.wait_connection(args.wait)
            info = bsl.command(b'\x19', 0x31, 25)
            buffer_size = int.from_bytes(info[11:13], 'little')
            if buffer_size < 256:
                raise ValueError('Unexpected small BSL buffer')
            report['device_info'] = info.hex()
            log(f'BSL_DEVICE_INFO_CRC_OK: buffer={buffer_size}')
            if args.program:
                report['crc32'] = f'{program_image(bsl, image, logs / "auth_state.json", log):08X}'
            elif args.verify_only:
                unlock(bsl, logs / 'auth_state.json')
                report['crc32'] = f'{verify_image(bsl, image, logs / "auth_state.json", log):08X}'
            if args.program or args.verify_only:
                report['verified'] = True
                # TI specifies an ACK, followed by a system reset into the application.
                bsl.command(b'\x40')
                report['application_started'] = True
                log('START_APPLICATION_ACK; application UART still needs checking')
            else:
                log('PROBE_OK: no password, erase or program sent')
        except Exception as exc:
            report['error'] = str(exc)
            log('FAILED: ' + str(exc))
        finally:
            port.close()
            (logs / f'{tag}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 1 if 'error' in report else 0


if __name__ == '__main__':
    sys.exit(main())
