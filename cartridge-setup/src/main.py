import hashlib
import json
import os

if __package__:
    from .acquire_games import (
        ImageCacheDir,
        ListFileMaxNameBytes,
        asciiify,
        buildGameList,
        createTimestampedGameListPath,
        generatePrintableImageGrids,
        getImages,
        getLatestGameListPath,
        getMyGamesAndNames,
        removeMiscGames,
    )
    from .flash_games import gameLineKey, writeGamesSerial
else:
    from acquire_games import (
        ImageCacheDir,
        ListFileMaxNameBytes,
        asciiify,
        buildGameList,
        createTimestampedGameListPath,
        generatePrintableImageGrids,
        getImages,
        getLatestGameListPath,
        getMyGamesAndNames,
        removeMiscGames,
    )
    from flash_games import gameLineKey, writeGamesSerial

GAME_LIST_STEM = "batch_game_list_local"
UPLOAD_STATE_FILE = f"{GAME_LIST_STEM}.uploaded.json"


def _read_games(steam_library_path: str) -> dict[str, str]:
    games = asciiify(removeMiscGames(getMyGamesAndNames(steam_library_path)))
    return {app_id: name[:ListFileMaxNameBytes] for app_id, name in games.items()}


def _file_digest(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as game_list:
        for chunk in iter(lambda: game_list.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _show_sync_status(game_list_path: str, state_path: str) -> None:
    if not os.path.isfile(state_path):
        print("No successful upload is recorded for this setup.")
        return
    try:
        with open(state_path, "rt", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not read the previous upload record: {error}")
        return

    if not isinstance(state, dict):
        print("The previous upload record is invalid; reader synchronization is unknown.")
    elif not isinstance(state.get("sha256"), str):
        print("No successful upload is recorded for this setup.")
    elif state["sha256"] == _file_digest(game_list_path):
        print("This list matches the last uploaded list (the reader's current state is not independently verified).")
    else:
        print("This list differs from the last successfully uploaded list; the reader may be out of date.")


def _read_list_entries(game_list_path: str) -> list[str]:
    # every game in a list file, as the keys used for tag bookkeeping (see gameLineKey)
    entries = []
    with open(game_list_path, "rt") as game_list:
        for line in game_list:
            if line.startswith("<> Random games"):
                break
            key = gameLineKey(line)
            if key:
                entries.append(key)
    return entries


def _load_upload_record(state_path: str) -> dict:
    if not os.path.isfile(state_path):
        return {}
    try:
        with open(state_path, "rt", encoding="utf-8") as state_file:
            record = json.load(state_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not read the previous upload record: {error}")
        return {}
    return record if isinstance(record, dict) else {}


def _tagged_entries(record: dict, directory: str = ".") -> set[str] | None:
    # the games that already have a written tag, or None if that was never recorded
    ids = record.get("confirmed_game_ids")
    if isinstance(ids, list):
        tagged = {app_id for app_id in ids if isinstance(app_id, str) and app_id.isdecimal()}
        commands = record.get("confirmed_custom_commands")
        if isinstance(commands, list):
            tagged.update(command for command in commands if isinstance(command, str))
        return tagged

    filename = record.get("filename")
    if isinstance(filename, str):
        recorded_list = os.path.join(directory, filename)
        if os.path.isfile(recorded_list):
            return set(_read_list_entries(recorded_list))
    return None


def _save_upload_record(state_path: str, record: dict, tagged: set[str], uploaded_list: str | None = None) -> None:
    # uploaded_list is only given after a complete upload, the tagged set is saved every time
    record["confirmed_game_ids"] = sorted((entry for entry in tagged if entry.isdecimal()), key=int)
    record["confirmed_custom_commands"] = sorted(entry for entry in tagged if not entry.isdecimal())
    if uploaded_list:
        record["filename"] = os.path.basename(uploaded_list)
        record["sha256"] = _file_digest(uploaded_list)
    temporary_path = f"{state_path}.tmp"
    with open(temporary_path, "wt", encoding="utf-8") as state_file:
        json.dump(record, state_file, indent=2)
        state_file.write("\n")
    os.replace(temporary_path, state_path)


def _ask_tagged_baseline(read_input, directory: str = ".") -> set[str]:
    # asked once, when there is no record of which tags exist
    candidates = sorted(name for name in os.listdir(directory) if name.startswith(GAME_LIST_STEM) and name.endswith((".txt", ".bak")))
    if not candidates:
        return set()

    print("There is no record of which game tags have already been written.")
    print("Which list matches the tags you already have?")
    print("\t[0] - none, no tags have been written yet")
    for i, name in enumerate(candidates, start=1):
        print(f"\t[{i}] - {name} ({len(set(_read_list_entries(os.path.join(directory, name))))} games)")
    while True:
        choice = read_input("(Enter a number) >> ").strip()
        if choice.isdecimal() and int(choice) <= len(candidates):
            break
    if int(choice) == 0:
        return set()
    return set(_read_list_entries(os.path.join(directory, candidates[int(choice) - 1])))


def _ask_choice(read_input, prompt: str, choices: set[str]) -> str:
    while True:
        choice = read_input(prompt).lower().strip()
        if choice in choices:
            return choice
        print(f"Please choose one of: {', '.join(sorted(choices))}")


def main(input_fn=None) -> None:
    read_input = input if input_fn is None else input_fn
    default_steam_path = "C:/Program Files (x86)/Steam"
    previous_game_list = getLatestGameListPath()
    state_path = UPLOAD_STATE_FILE
    record = _load_upload_record(state_path)
    tagged = _tagged_entries(record)
    if tagged is None:
        tagged = _ask_tagged_baseline(read_input)
        _save_upload_record(state_path, record, tagged)
        print(f"Recorded {len(tagged)} games as already tagged.")
    action = "build"
    use_difference = False

    if previous_game_list:
        print(f"Found existing game list: {previous_game_list}")
        choice = _ask_choice(
            read_input,
            "Would you like to (A) start a new list, (B) build cards for newly installed games, " "or (C) use this list without rebuilding? (A/B/C) >> ",
            {"a", "b", "c"},
        )
        if choice == "c":
            action = "upload_existing"
        elif choice == "b":
            use_difference = True

    if action == "build":
        steam_install_path = read_input(f'Is Steam installed at "{default_steam_path}"? (y/n) >> ')
        if steam_install_path.lower().strip() in {"y", "yes"}:
            steam_install_path = default_steam_path
        else:
            steam_install_path = read_input("Enter the location of your Steam install, e.g. G:/Programs/Steam\n>> ")

        steam_library_path = read_input(f'Are your Steam games installed at "{default_steam_path}"? (y/n) >> ')
        if steam_library_path.lower().strip() in {"y", "yes"}:
            steam_library_path = default_steam_path
        else:
            steam_library_path = read_input("Enter the location of your Steam library, e.g. G:/Games/Steam\n>> ")

        need_vr_tags = read_input("Do you need tags for your VR titles? Advanced option, takes longer. (y/n) >> ").lower().strip() in {"y", "yes"}

        all_games = _read_games(steam_library_path)
        printable_games = all_games
        if use_difference:
            printable_games = {app_id: name for app_id, name in all_games.items() if app_id not in tagged}
            print(f"Found {len(printable_games)} games without a tag.")

        if printable_games:
            getImages("steam", steam_install_path, printable_games, ImageCacheDir)
            page_count = generatePrintableImageGrids(ImageCacheDir)
            print(f'You can now print the {page_count}-page "printer_sheets.pdf"')
            os.startfile("printer_sheets.pdf")
        else:
            print("No new games to create printable cards for.")

        game_list_path = createTimestampedGameListPath()
        buildGameList(game_list_path, all_games, doRequests=need_vr_tags)
        print(f"Wrote complete game list: {game_list_path}")
    else:
        game_list_path = previous_game_list

    _show_sync_status(game_list_path, state_path)
    if read_input("Upload this game list to the reader now? (y/n) >> ").lower().strip() in {"y", "yes"}:
        all_entries = set(_read_list_entries(game_list_path))
        pending = all_entries - tagged
        print(f"Current list: {len(all_entries)} games; {len(all_entries) - len(pending)} already tagged; {len(pending)} tag entries are pending.")
        print(f"Sending {len(pending)} new tag entries and refreshing the full randomizer pool (reader limit: 255 games).")
        print("After the last game, the reader waits for your randomizer cartridge before it accepts the random games list.")
        result = writeGamesSerial(game_list_path, only_entries=pending)

        written = result.confirmed_game_ids & pending
        tagged.update(written)
        _save_upload_record(state_path, record, tagged, uploaded_list=game_list_path if result.success else None)
        print(f"{len(written)} game tags were written and recorded.")
        if result.success:
            print(f"Recorded {os.path.basename(game_list_path)} as the last successfully uploaded list.")
        else:
            print("Upload was not confirmed; the random games list on the reader may be out of date.")
        if pending - written:
            print(f"{len(pending - written)} game tags were not written; they will be offered again next time.")
    else:
        print("Upload deferred; your physical library may not match the current game list.")


if __name__ == "__main__":
    main()
