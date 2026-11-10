import threading

import pytest

from src import flash_games
from src.flash_games import UploadResult, _transfer_game_list, writeGamesSerial


class FakeSerialReader:
    def __init__(self, incoming, on_read=None):
        self.incoming = list(incoming)
        self.writes = []
        self.on_read = on_read

    @property
    def in_waiting(self):
        return len(self.incoming)

    def readline(self):
        line = self.incoming.pop(0)
        if self.on_read:
            self.on_read(line)
        return line

    def write(self, data):
        self.writes.append(data)


def test_transfer_game_list_with_fake_serial_reader(tmp_path):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\nRegularGame:123:N\n<> Random games\n123\n4567\n\n", encoding="utf-8")
    reader = FakeSerialReader([b"<NEXTGAME>\r\n", b"<NEXTGAME>\r\n", b"<RANDOMGAMES>\r\n", b"<EXIT>\r\n"])

    result = _transfer_game_list(reader, str(game_list), response_timeout=0.1)

    assert result == frozenset()
    assert reader.writes == [b"RegularGame:123:N\n", b"*\n", b"\x02", b"\x00\x00\x00{", b"\x00\x00\x11\xd7", b"*\n"]


def test_transfer_rejects_malformed_random_game_ids(tmp_path):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\n<> Random games\nnot-an-id\n", encoding="utf-8")
    reader = FakeSerialReader([b"<NEXTGAME>\n", b"<RANDOMGAMES>\n"])

    with pytest.raises(ValueError, match="Invalid app ID"):
        _transfer_game_list(reader, str(game_list), response_timeout=0.1)


def test_transfer_times_out_without_reader_response(tmp_path):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\n<> Random games\n", encoding="utf-8")
    reader = FakeSerialReader([])

    with pytest.raises(TimeoutError, match="Timed out"):
        _transfer_game_list(reader, str(game_list), response_timeout=0)


def test_upload_without_connected_hardware_does_not_attempt_serial_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\n", encoding="utf-8")

    assert not writeGamesSerial(str(game_list), port_list=[]).success


def test_write_games_serial_completes_with_fake_port_and_reader(tmp_path, monkeypatch):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\nRegularGame:123:N\n<> Random games\n123\n\n", encoding="utf-8")
    finished = threading.Event()
    reader = FakeSerialReader(
        [b"<NEXTGAME>\r\n", b"<NEXTGAME>\r\n", b"<RANDOMGAMES>\r\n", b"<EXIT>\r\n"], on_read=lambda line: finished.set() if b"<EXIT>" in line else None
    )

    class FakePort:
        name = "COM3"
        device = "COM3"
        description = "Fake reader"
        vid = 0x16C0
        pid = 0x0477

    class FakeSerialContext:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return reader

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(flash_games.serial, "Serial", FakeSerialContext)
    monkeypatch.setattr(flash_games, "sleep", lambda _: None)

    result = writeGamesSerial(str(game_list), port_list=[FakePort()], input_fn=lambda *_: (finished.wait(timeout=1) and ""), response_timeout=0.1)
    assert result == UploadResult(True)


def test_transfer_sends_only_delta_entries_and_full_randomizer_pool(tmp_path):
    full_list = tmp_path / "full.txt"
    full_list.write_text("<> generated\nOldGame:123:N\nNewGame:456:N\n<> Random games\n123\n456\n\n", encoding="utf-8")
    reader = FakeSerialReader([b"<NEXTGAME>\r\n", b"Prepare next cartridge\r\n", b"<NEXTGAME>\r\n", b"<RANDOMGAMES>\r\n", b"<EXIT>\r\n"])

    confirmed = _transfer_game_list(reader, str(full_list), response_timeout=0.1, only_entries={"456"})

    assert confirmed == frozenset({"456"})
    assert reader.writes == [b"NewGame:456:N\n", b"*\n", b"\x02", b"\x00\x00\x00{", b"\x00\x00\x01\xc8", b"*\n"]


def test_custom_command_line_is_sent_without_its_name(tmp_path):
    game_list = tmp_path / "games.txt"
    custom_line = 'MyTool Start-Process "D:\\Apps\\tool.exe"'
    game_list.write_text(f"<> generated\n# a comment\n{custom_line}\n<> Random games\n123\n\n", encoding="utf-8")
    reader = FakeSerialReader([b"<NEXTGAME>\r\n", b"Prepare next cartridge\r\n", b"<NEXTGAME>\r\n", b"<RANDOMGAMES>\r\n", b"<EXIT>\r\n"])

    confirmed = _transfer_game_list(reader, str(game_list), response_timeout=0.1)

    assert confirmed == frozenset({custom_line})
    assert reader.writes[0] == b'Start-Process "D:\\Apps\\tool.exe"\n'


def test_confirmed_writes_are_kept_when_the_transfer_fails(tmp_path):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\nFirst:1:N\nSecond:2:N\n<> Random games\n1\n\n", encoding="utf-8")
    reader = FakeSerialReader([b"<NEXTGAME>\r\n", b"Prepare next cartridge\r\n", b"<NEXTGAME>\r\n"])
    confirmed = set()

    with pytest.raises(TimeoutError):
        _transfer_game_list(reader, str(game_list), response_timeout=0, confirmed=confirmed)

    assert confirmed == {"1"}


def test_empty_delta_never_sends_skip_command_during_randomizer_upload(tmp_path, monkeypatch):
    game_list = tmp_path / "empty-delta.txt"
    game_list.write_text("<> generated\nOldGame:123:N\n<> Random games\n123\n\n", encoding="utf-8")
    finished = threading.Event()
    reader = FakeSerialReader([b"<NEXTGAME>\r\n", b"<RANDOMGAMES>\r\n", b"<EXIT>\r\n"], on_read=lambda line: finished.set() if b"<EXIT>" in line else None)

    class FakePort:
        name = "COM4"
        device = "COM4"
        description = "Fake reader"
        vid = 0x16C0
        pid = 0x0487

    class FakeSerialContext:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return reader

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(flash_games.serial, "Serial", FakeSerialContext)
    monkeypatch.setattr(flash_games, "sleep", lambda _: None)

    presses = []

    def input_fn(*_):
        # the first Enter is a stray press, the rest wait for the reader to finish
        presses.append(None)
        if len(presses) > 1:
            finished.wait(timeout=1)
        return ""

    result = writeGamesSerial(str(game_list), port_list=[FakePort()], input_fn=input_fn, response_timeout=0.1, only_entries=set())

    assert result.success
    assert b"X\n" not in reader.writes
