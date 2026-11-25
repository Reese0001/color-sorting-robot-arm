import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'vision/k230/robot_link.py'
spec = importlib.util.spec_from_file_location('robot_link', path)
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


def test_frame_wire_format_and_checksum():
    message = link.encode_frame(2, 123, True, 'RED', 320, 240, 1300, True)
    body, checksum = message.strip().split(b'*')
    assert body == b'V1,2,123,1,RED,320,240,1300,1,640'
    expected = 0
    for value in body:
        expected ^= value
    assert int(checksum, 16) == expected


def test_fragmented_observation_and_duplicate_request():
    parser = link.ObservationParser()
    assert not parser.feed(b'OBS,')
    assert parser.feed(b'42\r\n') and parser.epoch == 42
    assert not parser.feed(b'OBS,42\n')
    assert parser.feed(b'OBS,0\n') and parser.epoch == 0


def test_recognized_colors_without_v1_drop_poses_report_occupied():
    from types import SimpleNamespace
    sender = link.RobotLink.__new__(link.RobotLink)
    sender.parser = link.ObservationParser()
    sender.seq = 0
    messages = []
    def write(message):
        messages.append(message)
        return len(message)
    sender.uart = SimpleNamespace(write=write)
    for seq, color in enumerate(('YELLOW', 'PURPLE')):
        sender.send((color, 10, 10, 40, 40, 1600, 30, 30, None), True, True, False)
        assert messages[-1] == link.encode_frame(0, seq, True, 'UNKNOWN')


def test_overlong_and_bad_observation_do_not_change_epoch():
    parser = link.ObservationParser()
    parser.feed(b'OBS,5\n')
    for data in (b'OBS,-1\n', b'OBS,4294967296\n', b'OBS,1,2\n', b'A'*50+b'OBS,0\n', b'OBS,\x001\n'):
        assert not parser.feed(data)
        assert parser.epoch == 5
    assert parser.feed(b'OBS,6\n')
