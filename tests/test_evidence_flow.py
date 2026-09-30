import hashlib
import json
from pathlib import Path

import pytest

from _support import CANNED_TEXT, browse, env_for, lookup, record


@pytest.fixture()
def env(tmp_path):
    return env_for(tmp_path)


def test_end_to_end_record_and_lookup(env):
    rc, obs, _ = browse(
        "https://example.test/a",
        "session-a",
        "Evidence flow",
        env,
    )
    assert rc == 0
    assert obs["ok"] is True

    evidence = "opened in 2024"
    rc, rec, _ = record(
        obs["visit_id"],
        "The casino opened in 2024.",
        evidence,
        "session-a",
        env,
    )
    assert rc == 0
    assert rec["ok"] is True

    rc, found, _ = lookup(
        "claim",
        rec["claim_id"],
        "session-a",
        "current",
        env,
    )
    assert rc == 0
    assert found["claim"]["integrity_verified"] is True
    assert found["claim"]["exact_evidence"] == evidence
    assert found["observation"]["visit_id"] == obs["visit_id"]


def test_non_verbatim_evidence_is_rejected(env):
    rc, obs, _ = browse(
        "https://example.test/a",
        "session-a",
        "Evidence flow",
        env,
    )
    assert rc == 0

    rc, data, _ = record(
        obs["visit_id"],
        "Unsupported claim",
        "this text is not present",
        "session-a",
        env,
    )
    assert rc != 0
    assert data["ok"] is False
    assert "verbatim" in data["error"].lower()


def test_offsets_and_sha_are_stored(env):
    rc, obs, _ = browse(
        "https://example.test/a",
        "session-a",
        "Evidence flow",
        env,
    )
    assert rc == 0

    evidence = "enchanted emerald"
    rc, rec, _ = record(
        obs["visit_id"],
        "The page mentions enchanted emerald.",
        evidence,
        "session-a",
        env,
    )
    assert rc == 0

    rows = [
        json.loads(line)
        for line in Path(rec["ledger_path"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    claim = next(
        row for row in rows
        if row.get("claim_id") == rec["claim_id"]
    )
    start = CANNED_TEXT.find(evidence)
    assert claim["evidence_start_char"] == start
    assert claim["evidence_end_char"] == start + len(evidence)
    assert claim["evidence_sha256"] == hashlib.sha256(
        evidence.encode("utf-8")
    ).hexdigest()


def test_current_scope_isolates_sessions(env):
    rc, a, _ = browse(
        "https://example.test/a",
        "session-a",
        "A",
        env,
    )
    assert rc == 0
    rc, b, _ = browse(
        "https://example.test/b",
        "session-b",
        "B",
        env,
    )
    assert rc == 0

    rc, ca, _ = record(
        a["visit_id"],
        "A claim",
        "opened in 2024",
        "session-a",
        env,
    )
    assert rc == 0
    rc, cb, _ = record(
        b["visit_id"],
        "B claim",
        "two hundred tables",
        "session-b",
        env,
    )
    assert rc == 0

    rc, recent_a, _ = lookup(
        "recent",
        "10",
        "session-a",
        "current",
        env,
    )
    assert rc == 0
    ids = {claim["claim_id"] for claim in recent_a["claims"]}
    assert ca["claim_id"] in ids
    assert cb["claim_id"] not in ids


def test_all_scope_searches_across_runs(env):
    rc, a, _ = browse(
        "https://example.test/a",
        "session-a",
        "A",
        env,
    )
    assert rc == 0
    rc, b, _ = browse(
        "https://example.test/b",
        "session-b",
        "B",
        env,
    )
    assert rc == 0

    rc, ca, _ = record(
        a["visit_id"],
        "A claim",
        "opened in 2024",
        "session-a",
        env,
    )
    assert rc == 0
    rc, cb, _ = record(
        b["visit_id"],
        "B claim",
        "two hundred tables",
        "session-b",
        env,
    )
    assert rc == 0

    rc, recent, _ = lookup(
        "recent",
        "10",
        "session-a",
        "all",
        env,
    )
    assert rc == 0
    ids = {claim["claim_id"] for claim in recent["claims"]}
    assert ca["claim_id"] in ids
    assert cb["claim_id"] in ids


def test_tampered_evidence_is_reported(env):
    rc, obs, _ = browse(
        "https://example.test/a",
        "session-a",
        "Tamper",
        env,
    )
    assert rc == 0

    rc, rec, _ = record(
        obs["visit_id"],
        "Claim",
        "opened in 2024",
        "session-a",
        env,
    )
    assert rc == 0

    path = Path(rec["ledger_path"])
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row.get("claim_id") == rec["claim_id"]:
            row["evidence_sha256"] = "0" * 64

    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    rc, found, _ = lookup(
        "claim",
        rec["claim_id"],
        "session-a",
        "current",
        env,
    )
    assert rc == 0
    assert found["claim"]["integrity_verified"] is False
    assert "Evidence SHA-256 mismatch." in found["claim"]["integrity_errors"]
