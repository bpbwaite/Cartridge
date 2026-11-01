import serial
import serial.tools.list_ports
import threading
from time import time, sleep


def writeGamesSerial(infile_serial: str, flashingThisRun: dict[str, str] = {}):

    # flashingThisRun not yet implemented sorry

    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No ports found, aborting upload")
        return
    print("Port enumeration:")
    port_dict = {}
    for ii, port in enumerate(ports):
        i = ii + 1
        port_dict[i] = port
        print(f"\t[{i}] - {port.name}:{port.device} - {port.description}", end="")
        if port.vid == 0x16C0 and port.pid >= 0x0477 and port.pid <= 0x0488:
            print(" <-- Teensy!", end="")
    print()

    teensy_port = ""
    if len(port_dict) == 1 and port_dict[1].vid == 0x16C0:
        print(f"Automatically found Teensy on {port_dict[1].name}")
        teensy_port = port_dict[1].name
    else:
        print("Please choose a COM port for uploading")
        while True:
            choice = input("(Enter a number) >> ")
            if not choice.isnumeric():
                continue
            choice = int(choice)
            if choice in port_dict:
                break
        teensy_port = port_dict[int(choice)].name

    try:
        with serial.Serial(port=teensy_port, timeout=1) as S:
            sleep(1)

            # fork, main thread continues to handle user input
            def serial_monitor_routine():
                def echo() -> str:
                    while S.in_waiting == 0:
                        sleep(0.01)
                    from_teensy = S.readline().decode(errors="replace").rstrip()
                    print(f"[{time():.3f}] -> {from_teensy}")
                    return from_teensy

                try:
                    with open(infile_serial, "rt") as F:
                        header = F.readline().rstrip()
                        print(f"File header: {header}")
                        while True:
                            if "<NEXTGAME>" in echo():
                                game = F.readline()
                                while game[0] == "#":
                                    game = F.readline()
                                if "<>" in game:
                                    S.write("*\n".encode())  # done
                                    # move on to random section
                                    break
                                elif "Start-Process" in game:
                                    # custom path game
                                    gameName = game.split(" ", 1)[0]
                                    gameCommand = game.split(" ", 1)[
                                        1
                                    ]  # get command from line where line is GameNameOneWord (space) command
                                    print(f"CUSTOM: {gameName}")
                                    print(f"CUSTOM: {gameCommand}")
                                    S.write(gameCommand.encode())
                                else:
                                    S.write(game.encode())

                        while not ("<RANDOMGAMES>" in echo()):
                            pass

                        appIDs = []
                        while True:
                            id = F.readline().strip()
                            if not id or len(id) <= 1:
                                break
                            appIDs.append(int(id))
                        S.write(bytes([len(appIDs)]))

                    print(f"Writing {len(appIDs)} appIDs")
                    for id in appIDs:
                        # print(f'ID:<{id}>')
                        S.write(
                            bytes(
                                [
                                    (id & 0xFF000000) >> 24,
                                    (id & 0x00FF0000) >> 16,
                                    (id & 0x0000FF00) >> 8,
                                    (id & 0x000000FF) >> 0,
                                ]
                            )
                        )
                    S.write("*\n".encode())  # done

                    # Echo until thread is forced to exit
                    while not ("<EXIT>" in echo()):
                        pass

                except serial.SerialException as e:
                    pass
                    # print(f'Subroutine thread disconnected ({e})')
                print(
                    f"Serial thread disconnected, press enter to exit"
                )  # continues in main function
                return

            coroutine = threading.Thread(target=serial_monitor_routine, daemon=True)  # args=(S,)
            coroutine.start()

            while True:
                if not coroutine.is_alive():
                    coroutine.join()
                    break
                _ = input()
                S.write("X\n".encode())

    except serial.SerialException as e:
        # print(f'Main thread disconnected ({e})')
        pass
    except KeyboardInterrupt:
        pass

    print("Done. Power cycle the reader before re-running this setup")
