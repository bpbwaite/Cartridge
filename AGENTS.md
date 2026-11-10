# Cartridge — notes for agents

Cartridge launches PC games from NFC tags. A Teensy 4.0 "Reader" with a PN532 reads a tag and types a `start steam://run/<appID>` command as a USB keyboard, so no software runs on the PC. A Python tool on the PC builds the game list, the printable cards, and writes the tags through the Reader.

## Rules

- **Do not modify `README.md`.** It is maintained by hand. Put anything an agent needs to know in this file instead.
- **Do not modify the firmware (`cartridge-firmware/`) unless explicitly asked.** Readers in use run the `v0.3.0-alpha` firmware and cannot be reflashed, so the setup tool must stay compatible with that firmware's serial protocol (below).
- You cannot test on hardware. Say so when reporting; do not present simulated or unit-test results as a hardware result.
- Game lists, the upload record, the image cache and `printer_sheets.pdf` in `cartridge-setup/` are the user's personal data (gitignored). Never edit or delete them; work on copies in a temp directory.
- Commit only when asked.

## Layout

| Path | What it is |
|---|---|
| `cartridge-setup/` | Python setup tool (the part most work happens in) |
| `cartridge-firmware/` | PlatformIO project for the Teensy 4.0 Reader |
| `cartridge-pcb/` | KiCad project for the Reader PCB |
| `hardware/` | STL files for the Reader and Cartridge |
| `images/` | Images used by the README |
| `old/` | Gitignored scratch material, not part of the project |

## Setup tool (`cartridge-setup/`)

Managed with `uv`; Python 3.11.9 or newer; Windows only (`os.startfile`, Steam paths, COM ports). Run every command from `cartridge-setup/`, because the tool reads and writes its data files in the current directory.

```
uv run python src/main.py     # run the tool (interactive)
uv run pytest                 # tests
uv run black src tests        # formatter, line length 160
```

Style: match the existing code — camelCase public functions (`getGamesFromFile`), `_snake_case` private helpers, short lowercase comments, black with line length 160. The version lives in `pyproject.toml` and is mirrored in `uv.lock`.

### Modules

- `src/main.py` — the interactive flow and the upload record.
- `src/acquire_games.py` — reads Steam `appmanifest_*.acf` files, filters and shortens names, copies cover art into `copied_images_cache/`, lays out `printer_sheets.pdf` (6x7 cards per US-letter page at 300 ppi), and writes the game list file.
- `src/flash_games.py` — talks to the Reader over serial (`writeGamesSerial`).

### Data files (all in the working directory, all gitignored)

- `batch_game_list_local_YYYYMMDD_HHMMSS.txt` — a generated game list. A new one is written on every build; the newest one by timestamp is "the current list". Files with other suffixes (for example `..._my_copy.txt`) are ignored by that lookup but are offered as tagged-baseline candidates.
- `batch_game_list_local.uploaded.json` — the upload record.
- `copied_images_cache/`, `printer_sheets.pdf` — rebuilt on every build that has new games.

### Game list format

```
<> Game list automatically generated on <date>
GameName:123456:N
OtherName Start-Process "D:\Apps\tool.exe"
# comment
<> Random games
123456
```

- Steam line: `Name:appID:VR`, where the name is ASCII alphanumeric, at most 16 characters, and VR is `Y` or `N`.
- Custom line (added by hand): one-word name, a space, then a `Start-Process ...` command.
- After `<> Random games`: one appID per line, at most 255, ended by a blank line or end of file. This is the pool the randomizer cartridge picks from.

### The upload record

`batch_game_list_local.uploaded.json` is the only memory of which tags physically exist:

- `confirmed_game_ids` and `confirmed_custom_commands` — the tagged set. A custom line is identified by its whole text (`gameLineKey` in `flash_games.py`).
- `filename` and `sha256` — the last list that was uploaded completely; used only for the status message.

Behaviour that must be preserved:

1. With no record, the tool asks once which `batch_game_list_local*` file matches the existing tags and saves the answer before doing anything else.
2. Pending games = current list minus the tagged set. Both the printable cards and the tag lines sent to the Reader use this; neither ever covers already-tagged games. The random games pool is always sent in full.
3. A game is added to the tagged set only when the Reader prints `Prepare next cartridge` for it. Skipped or failed games stay pending.
4. The tagged set is saved after every upload attempt, including failed and interrupted ones. `filename`/`sha256` change only after a complete upload.

Deleting the record makes the tool ask the baseline question again.

## Firmware (`cartridge-firmware/`)

PlatformIO, `env:teensy40`, Arduino framework. `src/main.cpp` holds the launcher loop and the batch-write mode, `src/util.cpp` the PN532/NTAG215 and keyboard helpers, `include/config.h` the pins and tunables. DIP switches select the mode (`include/util.h`); `0b111` is batch write, which is the mode the setup tool talks to.

### Serial protocol in batch-write mode (frozen at v0.3.0)

The reference host implementation is `writeGamesSerial` in `git show v0.3.0-alpha:generate_games.py`.

1. For each game the Reader clears its receive buffer, prints `<NEXTGAME>`, and reads one line.
   - `Name:appID:VR\n` writes a Steam tag.
   - A line starting with `Start-Process` writes a custom-command tag. The host strips the leading name from a custom list line and sends only the command.
   - `*\n` ends the game phase.
2. After a game line the Reader waits for a tag. Any byte received while it waits means "skip this game"; the host sends `X\n` when the user presses Enter.
3. On a successful write it prints `Prepare next cartridge`; on a failed one `Error writing tag, retrying soon` and moves on to the next game without retrying.
4. After `*` it waits for a tag, **overwrites it as the RANDOM cartridge**, prints `<RANDOMGAMES>`, then reads one count byte `n` followed by `n` big-endian 4-byte appIDs into EEPROM.
5. It prints `<EXIT>` and halts until power cycled.

Things that break a v0.3.0 Reader, so the host must never do them:

- Sending a line with fewer than two colons that does not start with `Start-Process`. The firmware dereferences a null pointer and hangs.
- Sending anything while the Reader is not waiting for a tag. A stray byte can be read as a game line or as the random games count. The host therefore only sends `X\n` between sending a game line and the Reader reporting that a tag was detected; this is the one intended difference from the v0.3.0 host, which sent `X\n` on every Enter.
- Sending more than 255 random appIDs (the count is one byte).

When changing `flash_games.py`, compare the bytes it sends with the v0.3.0 host for the same list and the same user actions.
