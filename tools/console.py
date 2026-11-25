"""MSPM0 debug terminal; prints responses while accepting commands."""
import argparse
import threading
import time


def main():
    import serial
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', help='e.g. COM7; USB-TTL connected to PA14/PA13')
    parser.add_argument('--restore', help='Replay POSE/GRIP lines only, never ARM/AUTO/JOG')
    args = parser.parse_args()
    with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=1) as device:
        stop = threading.Event()
        def reader():
            while not stop.is_set():
                data = device.readline()
                if data:
                    print(data.decode('ascii', errors='replace').rstrip(), flush=True)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            if args.restore:
                from pathlib import Path
                lines = Path(args.restore).read_text(encoding='utf-8-sig').splitlines()
                for line in lines:
                    if line.startswith(('POSE ', 'GRIP ')):
                        device.write((line.strip() + '\n').encode('ascii'))
                        time.sleep(0.15)
            print('Enter HELP; exit with QUIT or Ctrl+C (sends STOP).')
            while True:
                command = input().strip()
                if command.upper() == 'QUIT':
                    break
                if command:
                    device.write((command + '\n').encode('ascii'))
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            device.write(b'STOP\n')
            time.sleep(0.2)
            stop.set()
            thread.join(timeout=1)


if __name__ == '__main__':
    main()

