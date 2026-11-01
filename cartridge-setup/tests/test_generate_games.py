from src.acquire_games import asciiify


def test_asciiify_removes_non_ascii_and_non_alphanumeric_characters():
    assert asciiify({"123": "Café: 100%!"}) == {"123": "Caf100"}
