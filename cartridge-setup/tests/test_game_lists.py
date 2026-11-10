from datetime import datetime

from src import acquire_games


def test_asciiify_removes_non_ascii_and_non_alphanumeric_characters():
    assert acquire_games.asciiify({"123": "Café: 100%!"}) == {"123": "Caf100"}


def test_get_games_from_steam_manifests(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_12345.acf").write_text('"AppState"\n{\n\t"appid"\t"12345"\n\t"name"\t"Cafe: 100%!"\n}\n', encoding="utf-8")

    assert acquire_games.getMyGamesAndNames(str(tmp_path)) == {"12345": "Cafe: 100%!"}


def test_remove_misc_games_matches_case_insensitive_tokens_before_truncation(capsys):
    games = {"1": "Demo: A Long Game Title", "2": "A Very Long Game Soundtrack", "3": "Demolition Crew", "4": "Wallpaper Engine"}

    result = acquire_games.removeMiscGames(games)

    assert result == {"3": "Demolition Crew"}
    assert "Demo: A Long Game Title" in capsys.readouterr().out


def test_remove_misc_games_handles_curly_apostrophe_in_friend_pass():
    games = {"1": "Game: Friend’s Pass"}

    assert acquire_games.removeMiscGames(games) == {}


def test_build_game_list_does_not_mutate_input_and_excludes_vr_from_random(tmp_path, monkeypatch):
    games = {"123": "RegularGame", "456": "VRGame"}
    monkeypatch.setattr(acquire_games, "isSteamGameVR", lambda appID: appID == "456")
    monkeypatch.setattr(acquire_games, "sleep", lambda _: None)
    target = tmp_path / "games.txt"

    acquire_games.buildGameList(str(target), games, doRequests=True)

    assert games == {"123": "RegularGame", "456": "VRGame"}
    content = target.read_text(encoding="utf-8")
    assert "RegularGame:123:N" in content
    assert "VRGame:456:Y" in content
    assert "\n123\n" in content
    assert "\n456\n" not in content


def test_timestamped_paths_are_unique_and_latest_is_selected(tmp_path):
    timestamp = datetime(2026, 11, 1, 19, 46, 0)
    first = acquire_games.createTimestampedGameListPath(str(tmp_path), timestamp)
    (tmp_path / first.split("\\")[-1]).touch()
    second = acquire_games.createTimestampedGameListPath(str(tmp_path), timestamp)
    (tmp_path / second.split("\\")[-1]).touch()

    assert first.endswith("batch_game_list_local_20261101_194600.txt")
    assert second.endswith("batch_game_list_local_20261101_194600_1.txt")
    assert acquire_games.getLatestGameListPath(str(tmp_path)) == second


def test_latest_timestamped_list_takes_precedence_over_legacy_names(tmp_path):
    legacy = tmp_path / acquire_games.LegacyGameListFile
    legacy.write_text("legacy", encoding="utf-8")
    timestamped = tmp_path / "batch_game_list_local_20261101_194600.txt"
    timestamped.write_text("new", encoding="utf-8")

    assert acquire_games.getLatestGameListPath(str(tmp_path)) == str(timestamped)


def test_legacy_list_is_used_when_no_timestamped_list_exists(tmp_path):
    legacy = tmp_path / acquire_games.LegacyGameListFile
    legacy.write_text("legacy", encoding="utf-8")

    assert acquire_games.getLatestGameListPath(str(tmp_path)) == str(legacy)


def test_get_games_from_file_accepts_single_character_names(tmp_path):
    game_list = tmp_path / "games.txt"
    game_list.write_text("<> generated\nA:123:N\n", encoding="utf-8")

    assert acquire_games.getGamesFromFile(str(game_list)) == {"123": "A"}


def test_delete_images_cache_removes_nested_files(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "cached-image.jpg").write_bytes(b"image")

    acquire_games.deleteImagesCache(str(cache))

    assert not cache.exists()
