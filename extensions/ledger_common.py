"""
Shared ledger infrastructure for the per-run research evidence ledger.

Every research run gets its own append-only .jsonl file under the ledger
directory (RESEARCH_LEDGER_DIR, default /workspace/research/ledgers). An
atomic index.json registry records each ledger and maps the originating
session to its ledger. The legacy single-file ledger is preserved and
registered in the registry without inventing metadata.

Environment overrides (used by tests):
  RESEARCH_LEDGER_DIR    -> directory for per-run ledgers + index.json
  RESEARCH_LEGACY_LEDGER -> path of the legacy evidence-ledger.jsonl
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

INDEX_SCHEMA_VERSION = 1
RECORD_SCHEMA_VERSION = 1

DEFAULT_LEDGER_DIR = "/workspace/research/ledgers"
DEFAULT_LEGACY_LEDGER = "/workspace/research/evidence-ledger.jsonl"
LEGACY_LEDGER_ID = "legacy-evidence-ledger"
MAX_SLUG_LEN = 40


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ledger_dir() -> Path:
    return Path(os.environ.get("RESEARCH_LEDGER_DIR") or DEFAULT_LEDGER_DIR)


def legacy_ledger_path() -> Path:
    return Path(os.environ.get("RESEARCH_LEGACY_LEDGER") or DEFAULT_LEGACY_LEDGER)


def index_path() -> Path:
    return ledger_dir() / "index.json"


def registry_lock_path() -> Path:
    return ledger_dir() / ".ledger.registry.lock"


def slugify(topic: str, max_len: int = MAX_SLUG_LEN) -> str:
    s = str(topic or "").lower()
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("_", " ")
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    s = s[:max_len].rstrip("-")
    return s if s else "research"


def file_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def make_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ledger-{stamp}-{uuid4().hex[:8]}"


def default_index() -> dict:
    return {"schema_version": INDEX_SCHEMA_VERSION, "ledgers": {}}


def _read_index_file() -> dict:
    p = index_path()
    if not p.exists():
        return default_index()
    data = p.read_text(encoding="utf-8")
    if not data.strip():
        return default_index()
    return json.loads(data)


def load_index() -> dict:
    p = index_path()
    if not p.exists():
        return default_index()
    with p.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            data = handle.read()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if not data.strip():
        return default_index()
    return json.loads(data)


def atomic_save_index(index: dict) -> None:
    p = index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{uuid4().hex[:8]}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


@contextmanager
def registry_locked():
    path = registry_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _register_legacy_if_missing(index: dict) -> None:
    existing = {str(e.get("path", "")) for e in index["ledgers"].values()}
    legacy = str(legacy_ledger_path())
    if legacy in existing:
        return
    index["ledgers"][LEGACY_LEDGER_ID] = {
        "ledger_id": LEGACY_LEDGER_ID,
        "topic": None,
        "slug": None,
        "created_at_utc": None,
        "updated_at_utc": None,
        "status": "active",
        "path": legacy,
        "session_id": None,
        "legacy": True,
    }


def unique_ledger_path(dir_: Path, date: str, slug: str) -> Path:
    n = 1
    while True:
        base = slug if n == 1 else f"{slug}-{n}"
        p = dir_ / f"{date}_{base}.jsonl"
        if not p.exists():
            return p
        n += 1


def resolve_ledger_for_session(session_id: str, topic: str = ""):
    sid = str(session_id or "").strip()
    topic = (topic or "").strip()

    if not sid:
        raise ValueError(
            "session_id is required; refusing to create or reuse an "
            "anonymous evidence ledger."
        )

    with registry_locked():
        dir_ = ledger_dir()
        dir_.mkdir(parents=True, exist_ok=True)
        index = _read_index_file()
        _register_legacy_if_missing(index)

        chosen = None
        for entry in list(index["ledgers"].values()):
            if entry.get("legacy") or entry.get("session_id") != sid:
                continue
            p = Path(entry.get("path", ""))
            if p.exists():
                chosen = entry
                break
            raise FileNotFoundError(
                "LEDGER_MISSING: session "
                f"{sid!r} is registered to ledger "
                f"{entry.get('ledger_id')!r} at {str(p)!r}, "
                "but that ledger file is missing. Refusing to create a "
                "replacement automatically because that would break "
                "evidence continuity. Restore the file or explicitly repair "
                "the registry."
            )

        if chosen is None:
            slug = slugify(topic) or slugify(sid) or "research"
            date = file_date()
            p = unique_ledger_path(dir_, date, slug)
            ledger_id = make_ledger_id()
            now = utc_now()
            chosen = {
                "ledger_id": ledger_id,
                "topic": topic,
                "slug": slug,
                "created_at_utc": now,
                "updated_at_utc": now,
                "status": "active",
                "path": str(p),
                "session_id": sid,
            }
            index["ledgers"][ledger_id] = chosen
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch(exist_ok=True)
        else:
            chosen["updated_at_utc"] = utc_now()

        atomic_save_index(index)
        return index["ledgers"][chosen["ledger_id"]], Path(chosen["path"])


def ensure_legacy_registered() -> dict:
    with registry_locked():
        index = _read_index_file()
        before_count = len(index["ledgers"])
        _register_legacy_if_missing(index)
        if len(index["ledgers"]) != before_count:
            atomic_save_index(index)
        return index


def all_ledger_entries():
    index = ensure_legacy_registered()
    return list(index["ledgers"].values())


def load_records(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["_ledger_path"] = str(path)
                records.append(record)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return records


def find_observation_by_visit_id(visit_id):
    for entry in all_ledger_entries():
        path = Path(entry.get("path", ""))
        if not path.exists():
            continue
        for record in load_records(path):
            if (
                record.get("record_type") == "browser_observation"
                and record.get("visit_id") == visit_id
            ):
                return entry, path, record
    return None, None, None


def append_record_to_path(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return record


def bump_ledger_updated(entry):
    ledger_id = entry.get("ledger_id")
    if not ledger_id:
        return entry
    with registry_locked():
        index = _read_index_file()
        entry = index["ledgers"].get(ledger_id)
        if entry is None:
            return None
        entry["updated_at_utc"] = utc_now()
        atomic_save_index(index)
    return entry


def all_records():
    pairs = []
    for entry in all_ledger_entries():
        path = Path(entry.get("path", ""))
        pairs.append((entry, load_records(path) if path.exists() else []))
    return pairs
