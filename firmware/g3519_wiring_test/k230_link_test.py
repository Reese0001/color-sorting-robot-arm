"""Run temporarily in CanMV IDE on the K230 to test both UART wires."""
import time
from machine import FPIOA, UART

pins = FPIOA()
pins.set_function(9, FPIOA.UART1_TXD, ie=0, oe=1, pu=1)
pins.set_function(10, FPIOA.UART1_RXD, ie=1, oe=0, pu=1)
uart = UART(UART.UART1, 115200)
buffer = b""
try:
    while True:
        data = uart.read(64)
        if data:
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.startswith(b"PING ") and line[5:].isdigit():
                    uart.write(b"PONG " + line[5:] + b"\n")
                    print("UART3 round trip request", line)
            if len(buffer) > 64:
                buffer = b""
        time.sleep_ms(5)
finally:
    uart.deinit()
