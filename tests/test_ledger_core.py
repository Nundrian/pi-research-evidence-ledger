import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from _support import EXT, env_for

import sys
sys.path.insert(0, str(EXT))
import ledger_common


@pytest.fixture()
def configured(tmp_path, monkeypatch):
    env = env_for(tmp_path)
    for key in (
        "RESEARCH_LEDGER_DIR",
        "RESEARCH_LEGACY_LEDGER",
    ):
        monkeypatch.setenv(key, env[key])
    return tmp_path


def test_same_session_reuses_ledger(configured):
    first, first_path = ledger_common.resolve_ledger_for_session(
        "session-a", "Topic A"
    )
    second, second_path = ledger_common.resolve_ledger_for_session(
        "session-a", "Different title"
    )
    assert first["ledger_id"] == second["ledger_id"]
    assert first_path == second_path


def test_different_sessions_get_different_ledgers(configured):
    a, ap = ledger_common.resolve_ledger_for_session("a", "Same title")
    b, bp = ledger_common.resolve_ledger_for_session("b", "Same title")
    assert a["ledger_id"] != b["ledger_id"]
    assert ap != bp
    assert ap.exists() and bp.exists()


def test_filename_collision_is_safe(configured):
    _, ap = ledger_common.resolve_ledger_for_session("a", "Shared")
    _, bp = ledger_common.resolve_ledger_for_session("b", "Shared")
    assert ap.name != bp.name
    assert bp.stem.endswith("-2")


def test_empty_session_is_rejected(configured):
    with pytest.raises(ValueError):
        ledger_common.resolve_ledger_for_session("", "No session")


def test_missing_registered_ledger_fails_safely(configured):
    entry, path = ledger_common.resolve_ledger_for_session("lost", "Lost")
    path.unlink()
    with pytest.raises(FileNotFoundError, match="LEDGER_MISSING"):
        ledger_common.resolve_ledger_for_session("lost", "Lost")


def test_legacy_registration_does_not_invent_metadata(configured):
    legacy = Path(
        ledger_common.legacy_ledger_path()
    )
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        '{"record_type":"browser_observation","visit_id":"legacy"}\n',
        encoding="utf-8",
    )

    index = ledger_common.ensure_legacy_registered()
    entry = index["ledgers"][ledger_common.LEGACY_LEDGER_ID]
    assert entry["legacy"] is True
    assert entry["topic"] is None
    assert entry["session_id"] is None
    assert entry["created_at_utc"] is None


def test_concurrent_sessions_never_share_ledger(configured):
    def create(i):
        entry, path = ledger_common.resolve_ledger_for_session(
            f"session-{i}", "Concurrent"
        )
        return entry["ledger_id"], str(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create, range(12)))

    ids = [x[0] for x in results]
    paths = [x[1] for x in results]
    assert len(set(ids)) == len(ids)
    assert len(set(paths)) == len(paths)


def test_append_is_jsonl_and_loadable(configured):
    _, path = ledger_common.resolve_ledger_for_session("s", "Append")
    ledger_common.append_record_to_path(
        path,
        {"record_type": "test", "value": 1},
    )
    ledger_common.append_record_to_path(
        path,
        {"record_type": "test", "value": 2},
    )
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [r["value"] for r in rows] == [1, 2]
