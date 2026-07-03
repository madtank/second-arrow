import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "find_talks.py"
SPEC = importlib.util.spec_from_file_location("find_talks", MODULE_PATH)
find_talks = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(find_talks)


def test_search_flattens_entries(monkeypatch):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, target, download=True):
            assert download is False
            captured["target"] = target
            return {
                "entries": [
                    {
                        "title": "Unentangled Knowing",
                        "channel": "dhammatalks",
                        "duration": 900.0,
                        "url": "https://youtu.be/abc",
                    },
                    None,
                    {"title": "No duration", "uploader": "someone", "url": "u2"},
                ]
            }

    monkeypatch.setattr(find_talks, "_ydl", lambda: FakeYoutubeDL)

    rows = find_talks.search("thanissaro feelings", limit=3)

    assert captured["target"] == "ytsearch3:thanissaro feelings"
    assert captured["opts"]["extract_flat"] is True
    assert captured["opts"]["no_warnings"] is True
    assert len(rows) == 2
    assert rows[0] == {
        "title": "Unentangled Knowing",
        "channel": "dhammatalks",
        "duration": 900,
        "url": "https://youtu.be/abc",
    }
    assert rows[1]["channel"] == "someone"
    assert rows[1]["duration"] is None


def test_search_download_error_becomes_a_clean_exit(monkeypatch):
    class FakeDownloadError(Exception):
        pass

    class FakeYoutubeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, target, download=True):
            raise FakeDownloadError("HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(find_talks, "_ydl", lambda: FakeYoutubeDL)
    monkeypatch.setattr(find_talks, "_download_error", lambda: FakeDownloadError)

    with pytest.raises(SystemExit) as excinfo:
        find_talks.search("thanissaro anger")

    assert str(excinfo.value).startswith("search failed:")
    assert "429" in str(excinfo.value)


def test_main_prints_json_lines(monkeypatch, capsys):
    row = {"title": "T", "channel": "C", "duration": 60, "url": "u"}
    calls = []

    def fake_search(query, limit=5):
        calls.append((query, limit))
        return [row]

    monkeypatch.setattr(find_talks, "search", fake_search)

    find_talks.main(["some query", "--limit", "2"])

    assert calls == [("some query", 2)]
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0]) == row
