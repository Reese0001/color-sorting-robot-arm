"""Generate/send deterministic K230 test frames. No servo commands are sent."""
import argparse
import time
def packet(seq, scene):
    slots = {
        'none': (-1,-1,0,-1,-1,0,-1,-1,0),
        'red': (320,240,5120,-1,-1,0,-1,-1,0),
        'green': (-1,-1,0,320,240,5120,-1,-1,0),
        'blue': (-1,-1,0,-1,-1,0,320,240,5120),
        'three': (320,240,5120,180,260,4800,150,300,4300),
    }[scene]
    body = ','.join(map(str, ('T',seq & 65535,90,90)+slots))
    checksum = 0
    for b in body.encode('ascii'): checksum ^= b
    return ('@%s*%02X\r\n' % (body,checksum)).encode('ascii')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', help='USB-TTL port connected to K230 input PA18, e.g. COM5')
    p.add_argument('--scene', choices=['none','red','green','blue','three'], default='red')
    p.add_argument('--count', type=int, default=50)
    p.add_argument('--bad-checksum', action='store_true')
    a=p.parse_args()
    if not a.port:
        print(repr(packet(42,a.scene))); return
    try:
        import serial
    except ImportError:
        p.error('Sending needs pyserial: python -m pip install pyserial. No serial writes made.')
    with serial.Serial(a.port,115200,timeout=0.2,write_timeout=1) as port:
        for seq in range(a.count):
            data=packet(seq,a.scene)
            if a.bad_checksum:
                checksum=int(data[-4:-2],16)^1
                data=data[:-4]+('%02X'%checksum).encode()+b'\r\n'
            port.write(data); print(data.decode().strip()); time.sleep(0.1)
if __name__ == '__main__': main()
