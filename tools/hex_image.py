"""Strict Intel HEX validation shared by packaging and the MAIN-only uploader."""
import struct


def check_hex(path):
    memory = {}
    base = 0
    ended = False
    for line in path.read_text(encoding='ascii').splitlines():
        assert line.startswith(':') and not ended, 'Invalid HEX line or data after EOF'
        data = bytes.fromhex(line[1:])
        assert len(data) == data[0] + 5 and sum(data) % 256 == 0, 'HEX checksum/length'
        count, addr, kind = data[0], int.from_bytes(data[1:3], 'big'), data[3]
        body = data[4:4+count]
        if kind == 0:
            for offset, byte in enumerate(body):
                address = base + addr + offset
                assert 0 <= address < 0x20000 and address not in memory, 'Non-MAIN or overlapping HEX'
                memory[address] = byte
        elif kind == 1:
            assert count == 0
            ended = True
        elif kind == 2:
            assert count == 2
            base = int.from_bytes(body, 'big') << 4
        elif kind == 4:
            assert count == 2
            base = int.from_bytes(body, 'big') << 16
        elif kind in (3, 5):
            assert count == 4
        else:
            raise ValueError('Unsupported HEX record')
    assert ended and memory, 'Missing EOF/data'
    stack, reset = struct.unpack('<II', bytes(memory[i] for i in range(8)))
    assert 0x20200000 < stack <= 0x20208000 and stack % 8 == 0, 'Invalid stack vector'
    assert reset & 1 and (reset & ~1) in memory, 'Invalid reset vector'
    return dict(data_bytes=len(memory), first=hex(min(memory)), last=hex(max(memory)),
                initial_sp=hex(stack), reset_vector=hex(reset), main_flash_only=True)

