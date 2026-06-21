"""Tests fuer den optionalen GitHub-Versionsabgleich (ohne echten Netzzugriff)."""
import json
from contextlib import contextmanager

import fh6tracker.update_check as uc


def test_version_parsing():
    assert uc._ver("v0.2.0") == (0, 2, 0)
    assert uc._ver("0.3.1") == (0, 3, 1)
    assert uc._ver("") == ()
    assert uc._ver("1.2") < uc._ver("1.10")     # numerisch, nicht lexikografisch


@contextmanager
def _fake_urlopen(payload):
    class _Resp:
        def read(self):
            return json.dumps(payload).encode("utf-8")
    yield _Resp()


def test_fetch_latest_newer_version(monkeypatch):
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen(
                            {"tag_name": "v0.3.0",
                             "html_url": "https://example/releases/v0.3.0"}))
    info = uc.fetch_latest("0.2.0")
    assert info == {"latest": "0.3.0",
                    "url": "https://example/releases/v0.3.0"}


def test_fetch_latest_same_or_older_returns_none(monkeypatch):
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen({"tag_name": "v0.2.0"}))
    assert uc.fetch_latest("0.2.0") is None       # gleich -> kein Hinweis
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen({"tag_name": "v0.1.0"}))
    assert uc.fetch_latest("0.2.0") is None       # aelter -> kein Hinweis


def test_no_suggestion_when_installed_is_newer(monkeypatch):
    # NexusMods-Patch vorab: installiert 0.2.1, GitHub steht noch auf 0.2.0.
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen({"tag_name": "v0.2.0"}))
    assert uc.fetch_latest("0.2.1") is None         # aeltere GitHub-Version -> kein Vorschlag


def test_numeric_order_not_lexicographic(monkeypatch):
    # 0.2.10 ist NEUER als 0.2.9 (Zahl, nicht Text) -> wird vorgeschlagen.
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen({"tag_name": "v0.2.10"}))
    info = uc.fetch_latest("0.2.9")
    assert info and info["latest"] == "0.2.10"
    # umgekehrt: installiert 0.2.10, GitHub 0.2.9 -> kein Downgrade-Vorschlag
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen({"tag_name": "v0.2.9"}))
    assert uc.fetch_latest("0.2.10") is None


def test_fetch_latest_handles_network_error(monkeypatch):
    def boom(*a, **k):
        raise uc.URLError("offline")
    monkeypatch.setattr(uc.urllib.request, "urlopen", boom)
    assert uc.fetch_latest("0.2.0") is None       # offline -> None, kein Crash


def test_fetch_latest_handles_garbage(monkeypatch):
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _fake_urlopen(["not", "a", "dict"]))
    assert uc.fetch_latest("0.2.0") is None


def test_cached_latest_avoids_repeat_calls(monkeypatch):
    uc._cache.update({"t": 0.0, "val": None})       # Cache leeren
    calls = {"n": 0}

    def one(*a, **k):
        calls["n"] += 1
        return _fake_urlopen({"tag_name": "v0.9.0"})

    monkeypatch.setattr(uc.urllib.request, "urlopen", one)
    first = uc.cached_latest("0.2.0")
    second = uc.cached_latest("0.2.0")              # innerhalb TTL -> aus Cache
    assert first == second == {"latest": "0.9.0",
                               "url": uc._RELEASES_PAGE}
    assert calls["n"] == 1                          # nur EIN echter Request
