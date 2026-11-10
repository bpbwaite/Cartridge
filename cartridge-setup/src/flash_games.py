import re
import threading
from dataclasses import dataclass
from time import monotonic, sleep, time

import serial
import serial.tools.list_ports


@dataclass(frozen=True)
class UploadResult:
    success: bool
    confirmed_game_ids: frozenset[str] = frozenset()  # entries (see gameLineKey) the reader reported as written, even if the upload did not finish

    def __bool__(self) -> bool:
        return self.success


class _UploadStopped(Exception):
    pass


def gameLineKey(line: str) -> str | None:
    # identity of a game-list line for tag bookkeeping: the appID, or the whole line for a custom command
    line = line.strip()
    if not line or line.startswith(("#", "<")):
        return None
    if "Start-Process" in line:
        return line
    match = re.match(r"^[^:\s]+:(\d+):", line)
    return match.group(1) if match else None


def _is_teensy(port) -> bool:
    return port.vid == 0x16C0 and port.pid is not None and 0x0477 <= port.pid <= 0x0488


def _read_game_list(infile_serial: str) -> tuple[str, list[str], list[int]]:
    # parse and validate the whole file before anything is sent to the reader
    with open(infile_serial, "rt") as game_list:
        header = game_list.readline().rstrip()
        if not header:
            raise ValueError(f"Game list is empty: {infile_serial}")

        games: list[str] = []
        for line in game_list:
            if line.startswith("<>"):
                break
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if gameLineKey(line) is None:
                # the reader cannot parse a line like this
                print(f"Skipping malformed line: {line.rstrip()}")
                continue
            games.append(line if line.endswith("\n") else line + "\n")
        else:
            raise ValueError(f"Game list has no random-games section: {infile_serial}")

        app_ids: list[int] = []
        for line in game_list:
            app_id = line.strip()
            if not app_id:
                break
            if not app_id.isdecimal():
                raise ValueError(f"Invalid app ID in random-games section: {app_id}")
            value = int(app_id)
            if value > 0xFFFFFFFF:
                raise ValueError(f"App ID exceeds the supported 32-bit range: {app_id}")
            app_ids.append(value)
            if len(app_ids) > 255:
                raise ValueError("Random-games section exceeds the 255-entry reader limit")

    return header, games, app_ids


def _echo(reader, response_timeout: float | None, stop: threading.Event | None = None) -> str:
    deadline = monotonic() + response_timeout if response_timeout is not None else None
    while True:
        while reader.in_waiting == 0:
            if stop is not None and stop.is_set():
                raise _UploadStopped
            if deadline is not None and monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for a response from the reader")
            sleep(0.01)
        response = reader.readline()
        if response:
            from_reader = response.decode(errors="replace").rstrip()
            print(f"[{time():.3f}] -> {from_reader}")
            return from_reader
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for a response from the reader")


def _wait_for_marker(reader, marker: str, response_timeout: float | None, on_line=None, stop: threading.Event | None = None) -> None:
    while True:
        line = _echo(reader, response_timeout, stop)
        if on_line:
            on_line(line)
        if marker in line:
            return


def _transfer_game_list(
    reader,
    infile_serial: str,
    response_timeout: float | None,
    only_entries: set[str] | None = None,
    game_phase: threading.Event | None = None,
    confirmed: set[str] | None = None,
    stop: threading.Event | None = None,
) -> frozenset[str]:
    # only_entries limits which game lines are sent (by gameLineKey); the random-games section is always sent in full
    # confirmed is filled in as the reader reports each tag write, so the caller keeps it even if the transfer fails
    confirmed = set() if confirmed is None else confirmed
    current_key: str | None = None

    def record_game_write(line: str) -> None:
        nonlocal current_key
        if "Preparing to write entry" in line or "Prepare next cartridge" in line:
            # a tag is on the reader, it is too late to skip
            if game_phase:
                game_phase.clear()
        if current_key and "Prepare next cartridge" in line:
            confirmed.add(current_key)
            current_key = None

    header, games, app_ids = _read_game_list(infile_serial)
    print(f"File header: {header}")
    if only_entries is not None:
        games = [game for game in games if gameLineKey(game) in only_entries]

    for game in games:
        _wait_for_marker(reader, "<NEXTGAME>", response_timeout, record_game_write, stop)
        current_key = gameLineKey(game)
        if "Start-Process" in game and not game.startswith("Start-Process"):
            # custom path game, the line is GameNameOneWord (space) command and the reader only wants the command
            game_name, game = game.split(" ", 1)
            print(f"CUSTOM: {game_name}")
            print(f"CUSTOM: {game.rstrip()}")
        reader.write(game.encode())
        if game_phase:
            game_phase.set()

    _wait_for_marker(reader, "<NEXTGAME>", response_timeout, record_game_write, stop)
    if game_phase:
        game_phase.clear()
    reader.write(b"*\n")  # done, move on to random section

    _wait_for_marker(reader, "<RANDOMGAMES>", response_timeout, stop=stop)
    print(f"Writing {len(app_ids)} appIDs")
    reader.write(bytes([len(app_ids)]))
    for app_id in app_ids:
        reader.write(app_id.to_bytes(4, byteorder="big"))
    reader.write(b"*\n")
    _wait_for_marker(reader, "<EXIT>", response_timeout, stop=stop)
    return frozenset(confirmed)


def writeGamesSerial(
    infile_serial: str, *, port_list=None, input_fn=None, response_timeout: float | None = None, only_entries: set[str] | None = None
) -> UploadResult:
    ports = serial.tools.list_ports.comports() if port_list is None else port_list
    if not ports:
        print("No ports found, aborting upload")
        return UploadResult(False)

    print("Port enumeration:")
    port_dict = {}
    for i, port in enumerate(ports, start=1):
        port_dict[i] = port
        print(f"\t[{i}] - {port.name}:{port.device} - {port.description}", end="")
        if _is_teensy(port):
            print(" <-- Teensy!", end="")
    print()

    read_input = input if input_fn is None else input_fn
    if len(port_dict) == 1 and _is_teensy(port_dict[1]):
        selected_port = port_dict[1].device
        print(f"Automatically found Teensy on {port_dict[1].name}")
    else:
        print("Please choose a COM port for uploading")
        while True:
            choice = read_input("(Enter a number) >> ")
            if choice.isnumeric() and int(choice) in port_dict:
                selected_port = port_dict[int(choice)].device
                break

    errors: list[Exception] = []
    transfer_succeeded = False
    confirmed: set[str] = set()
    game_phase = threading.Event()  # set while the reader is waiting for a tag, the only time a skip may be sent
    stop = threading.Event()
    try:
        with serial.Serial(port=selected_port, timeout=1) as reader:
            sleep(1)

            # fork, main thread continues to handle user input
            def serial_monitor_routine() -> None:
                nonlocal transfer_succeeded
                try:
                    _transfer_game_list(reader, infile_serial, response_timeout, only_entries, game_phase, confirmed, stop)
                except _UploadStopped:
                    return
                except (serial.SerialException, OSError, TimeoutError, ValueError) as error:
                    errors.append(error)
                else:
                    transfer_succeeded = True
                print("Serial thread disconnected, press enter to exit")  # continues in main function

            monitor = threading.Thread(target=serial_monitor_routine, daemon=True)
            monitor.start()

            try:
                while monitor.is_alive():
                    read_input()
                    # one skip per game, and nothing is sent unless the reader is waiting for a tag
                    if game_phase.is_set() and monitor.is_alive():
                        game_phase.clear()
                        reader.write(b"X\n")
            except (KeyboardInterrupt, EOFError):
                print("Upload interrupted")

            stop.set()
            monitor.join(timeout=5)
            if errors:
                print(f"Upload failed: {errors[0]}")
                return UploadResult(False, frozenset(confirmed))
            if not transfer_succeeded:
                print("Upload ended without a completed reader handshake")
                return UploadResult(False, frozenset(confirmed))

    except serial.SerialException as error:
        print(f"Could not communicate with reader on {selected_port}: {error}")
        return UploadResult(False, frozenset(confirmed))

    print("Done. Power cycle the reader before re-running this setup")
    return UploadResult(True, frozenset(confirmed))
