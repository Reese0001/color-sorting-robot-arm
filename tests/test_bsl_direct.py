"""No hardware: official wire vectors, parser corruption, write limits, fail-stop."""
from pathlib import Path
import io
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bsl_direct import BSL, packet, crc, validate_request, program_image, verify_image, SIZE, checked_image


class FakePort:
    def __init__(self, data):
        self.data = io.BytesIO(data)
        self.writes = []
    def read(self, n):
        return self.data.read(min(n, 1))  # Deliberately fragment every response.
    def write(self, b):
        self.writes.append(b)
        return len(b)
    def flush(self):
        pass
    def reset_input_buffer(self):
        pass


class AuthRecord:
    def __init__(self): self.text=None
    def exists(self): return self.text is not None
    def read_text(self): return self.text
    def write_text(self,text): self.text=text


class Tests(unittest.TestCase):
    def test_connection_in_fresh_and_existing_sessions(self):
        for response in [b'\0', bytes.fromhex('000802003b060da7f76b')]:
            p=FakePort(response)
            BSL(p).wait_connection(1)
            self.assertEqual(p.writes,[packet(b'\x12')])

    def test_official_vectors(self):
        for body, expected in [
            ('12', '800100123a6144de'),
            ('19', '80010019b2b89649'),
            ('21' + 'ff'*32, '80210021' + 'ff'*32 + '02aaf03d'),
            ('2300010000ff030000', '8009002300010000ff0300002be6bed8'),
            ('2600000000000c0000', '8009002600000000000c00001ce907e1'),
            ('40', '80010040e251215b')]:
            self.assertEqual(packet(bytes.fromhex(body)).hex(), expected)

    def test_response_and_crc(self):
        good = bytes.fromhex('000802003b0038029482')
        self.assertEqual(BSL(FakePort(good)).command(b'\x21'+b'\xff'*32, 0x3B, 2), b'\x3b\0')
        for pos in (0, 1, 2, 4, 5, 8, 9):
            bad = bytearray(good); bad[pos] ^= 1
            with self.assertRaises((ValueError, TimeoutError)):
                BSL(FakePort(bad)).command(b'\x21'+b'\xff'*32, 0x3B, 2)

    def test_write_boundaries(self):
        for addr in (0, SIZE-128):
            validate_request(b'\x20'+struct.pack('<I',addr)+bytes(128))
        for body in [b'\x30', b'\x15', b'\x24', b'\x52\x06',
                     b'\x21'+bytes(32), b'\x23'+struct.pack('<II',0,0x41c00000),
                     b'\x20'+struct.pack('<I',0x41c00000)+bytes(128),
                     b'\x20'+struct.pack('<I',SIZE-8)+bytes(128),
                     b'\x20'+struct.pack('<I',1)+bytes(128)]:
            with self.assertRaises(ValueError): validate_request(body)

    def test_read_only_limits(self):
        for command, length in [(0x26, 1024), (0x29, 512)]:
            validate_request(bytes([command])+struct.pack('<II',SIZE-length,length))
            for addr, count in [(SIZE-length+4,length),(0,0),(0x41c00000,length),(1,length)]:
                with self.assertRaises(ValueError):
                    validate_request(bytes([command])+struct.pack('<II',addr,count))
        with self.assertRaises(ValueError):validate_request(b'\x26'+struct.pack('<II',0,1020))

    def test_verify_only_sends_no_write_or_start(self):
        image,_=checked_image()
        payload=b'\x32'+struct.pack('<I',crc(image))
        p=FakePort(b'\0\x08\x05\0'+payload+struct.pack('<I',crc(payload)))
        self.assertEqual(verify_image(BSL(p),image,AuthRecord(),lambda x:None),crc(image))
        self.assertEqual([x[3] for x in p.writes],[0x26])

    def test_bad_password_never_erases_or_retries(self):
        payload=b'\x3b\x02'
        response=b'\0\x08\x02\0'+payload+struct.pack('<I',crc(payload))
        p=FakePort(response)
        state=AuthRecord()
        with self.assertRaises(ValueError):program_image(BSL(p),bytes(SIZE),state,lambda x:None)
        self.assertEqual(len(p.writes),1)
        with self.assertRaises(RuntimeError):program_image(BSL(p),bytes(SIZE),state,lambda x:None)
        self.assertEqual(len(p.writes),1)

    def test_program_and_verify(self):
        image,_=checked_image()
        good=bytes.fromhex('000802003b0038029482')
        payload=b'\x32'+struct.pack('<I',crc(image))
        p=FakePort(good*130+b'\0\x08\x05\0'+payload+struct.pack('<I',crc(payload)))
        self.assertEqual(program_image(BSL(p),image,AuthRecord(),lambda x:None),crc(image))
        self.assertEqual(len(p.writes),131)
        self.assertEqual([p.writes[i][3] for i in (0,1,2,-1)],[0x21,0x23,0x20,0x26])

    def test_program_error_stops_before_next_write(self):
        good=bytes.fromhex('000802003b0038029482')
        payload=b'\x3b\x05'
        error=b'\0\x08\x02\0'+payload+struct.pack('<I',crc(payload))
        p=FakePort(good*2+error)
        with self.assertRaises(ValueError):program_image(BSL(p),bytes(SIZE),AuthRecord(),lambda x:None)
        self.assertEqual(len(p.writes),3)

    def test_verify_mismatch_never_reports_verified(self):
        good=bytes.fromhex('000802003b0038029482')
        payload=b'\x32'+struct.pack('<I',crc(bytes(SIZE))^1)
        p=FakePort(good*130+b'\0\x08\x05\0'+payload+struct.pack('<I',crc(payload)))
        state=AuthRecord()
        with self.assertRaises(ValueError):program_image(BSL(p),bytes(SIZE),state,lambda x:None)
        self.assertNotIn('verified',state.read_text())


if __name__=='__main__':unittest.main()
