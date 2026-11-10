import json
from pathlib import Path

from src import main
from src.acquire_games import LegacyGameListFile
from src.flash_games import UploadResult


def test_upload_prompt_runs_each_run_and_records_only_success(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    legacy_list = tmp_path / LegacyGameListFile
    legacy_list.write_text("<> generated\nGame:123:N\n<> Random games\n123\n\n", encoding="utf-8")
    prompts = []

    def input_fn(prompt):
        prompts.append(prompt)
        if prompt.startswith("(Enter a number)"):
            return "0"
        return "c" if prompt.startswith("Would you like") else "y"

    monkeypatch.setattr(main, "writeGamesSerial", lambda *_args, **_kwargs: UploadResult(False))
    main.main(input_fn=input_fn)

    state_path = tmp_path / main.UPLOAD_STATE_FILE
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["confirmed_game_ids"] == []
    assert "sha256" not in state
    assert any("Upload this game list" in prompt for prompt in prompts)
    assert "Upload was not confirmed" in capsys.readouterr().out

    prompts.clear()
    monkeypatch.setattr(main, "writeGamesSerial", lambda *_args, **_kwargs: UploadResult(True, frozenset({"123"})))
    main.main(input_fn=input_fn)

    assert any("Upload this game list" in prompt for prompt in prompts)
    assert not any(prompt.startswith("(Enter a number)") for prompt in prompts)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["filename"] == LegacyGameListFile
    assert len(state["sha256"]) == 64
    assert state["confirmed_game_ids"] == ["123"]


def test_current_list_reports_if_it_differs_from_last_successful_upload(tmp_path, capsys):
    game_list = tmp_path / "games.txt"
    game_list.write_text("current", encoding="utf-8")
    state_path = tmp_path / "uploaded.json"
    state_path.write_text(json.dumps({"sha256": "stale"}), encoding="utf-8")

    main._show_sync_status(str(game_list), str(state_path))

    assert "reader may be out of date" in capsys.readouterr().out


def test_starting_over_does_not_require_a_legacy_backup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / LegacyGameListFile).write_text("<> generated\n", encoding="utf-8")
    monkeypatch.setattr(main, "_read_games", lambda _: {})
    responses = iter(["0", "a", "y", "y", "n", "n"])

    main.main(input_fn=lambda _: next(responses))

    assert list(tmp_path.glob("batch_game_list_local_*.txt"))


def test_new_run_prints_and_flashes_only_new_games_but_keeps_full_randomizer_pool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    previous_list = tmp_path / LegacyGameListFile
    previous_list.write_text("<> generated\nOldGame:100:N\n<> Random games\n100\n\n", encoding="utf-8")
    printed_game_ids = []
    upload = {}

    monkeypatch.setattr(main, "_read_games", lambda _: {"100": "OldGame", "200": "NewGame"})
    monkeypatch.setattr(main, "getImages", lambda _platform, _source, games, _cache: printed_game_ids.extend(games))
    monkeypatch.setattr(main, "generatePrintableImageGrids", lambda _: 1)
    monkeypatch.setattr(main.os, "startfile", lambda _: None, raising=False)

    def build_game_list(path, games, doRequests=False):
        with open(path, "wt", encoding="utf-8") as game_list:
            game_list.write("<> generated\n")
            for app_id, name in games.items():
                game_list.write(f"{name}:{app_id}:N\n")
            game_list.write("<> Random games\n100\n200\n\n")

    def write_games_serial(list_path, *, only_entries):
        upload["only_entries"] = only_entries
        upload["full"] = Path(list_path).read_text(encoding="utf-8")
        return UploadResult(True, frozenset({"200"}))

    monkeypatch.setattr(main, "buildGameList", build_game_list)
    monkeypatch.setattr(main, "writeGamesSerial", write_games_serial)
    responses = iter(["1", "b", "y", "y", "n", "y"])

    main.main(input_fn=lambda _: next(responses))

    assert printed_game_ids == ["200"]
    assert upload["only_entries"] == {"200"}
    assert "OldGame:100:N" in upload["full"]
    assert "NewGame:200:N" in upload["full"]
    assert "\n100\n200\n" in upload["full"]
    state = json.loads((tmp_path / main.UPLOAD_STATE_FILE).read_text(encoding="utf-8"))
    assert state["confirmed_game_ids"] == ["100", "200"]


def test_tagged_baseline_can_be_a_personal_copy_and_is_saved_before_upload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_game_list_local_20260325_120005_my_copy.txt").write_text("<> generated\nOldGame:100:N\n<> Random games\n100\n\n", encoding="utf-8")
    (tmp_path / "batch_game_list_local_20261101_204448.txt").write_text(
        "<> generated\nOldGame:100:N\nNewGame:200:N\n<> Random games\n100\n200\n\n", encoding="utf-8"
    )
    upload = {}

    def write_games_serial(list_path, *, only_entries):
        upload["list"] = Path(list_path).name
        upload["only_entries"] = only_entries
        upload["record"] = json.loads((tmp_path / main.UPLOAD_STATE_FILE).read_text(encoding="utf-8"))
        return UploadResult(False, frozenset({"200"}))

    monkeypatch.setattr(main, "writeGamesSerial", write_games_serial)
    responses = iter(["1", "c", "y"])

    main.main(input_fn=lambda _: next(responses))

    assert upload["list"] == "batch_game_list_local_20261101_204448.txt"
    assert upload["only_entries"] == {"200"}
    assert upload["record"]["confirmed_game_ids"] == ["100"]
    # the upload did not finish, but the tag that was written is still recorded
    state = json.loads((tmp_path / main.UPLOAD_STATE_FILE).read_text(encoding="utf-8"))
    assert state["confirmed_game_ids"] == ["100", "200"]
    assert "sha256" not in state


def test_skipped_games_remain_pending(tmp_path):
    state_path = tmp_path / main.UPLOAD_STATE_FILE
    main._save_upload_record(str(state_path), {}, {"100", 'Tool Start-Process "tool.exe"'})

    tagged = main._tagged_entries(main._load_upload_record(str(state_path)))

    assert tagged == {"100", 'Tool Start-Process "tool.exe"'}
    assert {"100", "200"} - set(tagged or ()) == {"200"}


def test_no_record_means_the_tagged_set_is_unknown(tmp_path):
    assert main._tagged_entries(main._load_upload_record(str(tmp_path / main.UPLOAD_STATE_FILE))) is None


def test_misc_game_filter_runs_before_game_name_truncation(monkeypatch):
    monkeypatch.setattr(main, "getMyGamesAndNames", lambda _: {"1": "ReallyLongGameName Soundtrack", "2": "A Good Game"})

    assert main._read_games("steam-library") == {"2": "AGoodGame"}
