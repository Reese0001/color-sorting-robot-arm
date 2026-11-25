"""Versioned K230/MSPM0 link. Protocol helpers import without board modules."""


def encode_frame(epoch, seq, calibrated, color, x=0, y=0, pixels=0, stable=False):
    body = "V1,{},{},{},{},{},{},{},{},640".format(
        epoch, seq, int(bool(calibrated)), color, x, y, pixels, int(bool(stable)))
    checksum = 0
    for value in body.encode():
        checksum ^= value
    return (body + "*{:02X}\n".format(checksum)).encode()


class ObservationParser:
    def __init__(self):
        self.epoch = 0
        self.buffer = bytearray()
        self.drop = False

    def feed(self, data):
        changed = False
        for value in data:
            if value == 13:
                continue
            if value == 10:
                if not self.drop:
                    try:
                        fields = self.buffer.decode().split(',')
                        if len(fields) == 2 and fields[0] == 'OBS' and fields[1].isdigit():
                            epoch = int(fields[1])
                            if 0 <= epoch <= 0xffffffff and epoch != self.epoch:
                                self.epoch, changed = epoch, True
                    except (ValueError, UnicodeError):
                        pass
                self.buffer = bytearray()
                self.drop = False
            elif len(self.buffer) >= 32 or value < 32 or value > 126:
                self.drop = True
            elif not self.drop:
                self.buffer.append(value)
        return changed


class RobotLink:
    def __init__(self):
        from machine import UART, FPIOA
        self.fpioa = FPIOA()
        self.fpioa.set_function(9, self.fpioa.UART1_TXD, ie=0, oe=1, pu=1)
        self.fpioa.set_function(10, self.fpioa.UART1_RXD, ie=1, oe=0, pu=1)
        self.uart = UART(UART.UART1, 115200)
        self.parser = ObservationParser()
        self.seq = 0

    def poll(self):
        data = self.uart.read(128)
        return self.parser.feed(data) if data else False

    def send(self, target, stable, calibrated, truly_empty):
        if target is None:
            message = encode_frame(self.parser.epoch, self.seq, calibrated,
                                   'NONE' if truly_empty else 'UNKNOWN')
        elif target[0] not in ('RED', 'GREEN', 'BLUE'):
            # V1 has taught drop poses for RGB only. The workspace is occupied.
            message = encode_frame(self.parser.epoch, self.seq, calibrated, 'UNKNOWN')
        else:
            message = encode_frame(self.parser.epoch, self.seq, calibrated,
                                   target[0], target[6], target[7], target[5], stable)
        self.seq = (self.seq + 1) & 0xffffffff
        written = self.uart.write(message)
        if written != len(message):
            raise OSError('Incomplete UART write; stop and check link')

    def close(self):
        self.uart.deinit()
