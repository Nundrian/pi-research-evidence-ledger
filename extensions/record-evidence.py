#!/usr/bin/env python3

import sys
import json
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import ledger_common

SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_claim_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"claim-{stamp}-{uuid4().hex[:8]}"


def fail(message):
    print(json.dumps(
        {
            "ok": False,
            "error": message,
        },
        ensure_ascii=False,
    ))
    sys.exit(1)


def find_observation(visit_id):
    entry, path, record = ledger_common.find_observation_by_visit_id(visit_id)

    if entry is None:
        fail(f"No browser observation found for visit ID: {visit_id}")

    return entry, path, record


def append_record(path, record):
    ledger_common.append_record_to_path(path, record)


def main():
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        fail(
            "Usage: record-evidence.py "
            "<visit_id> <claim> <exact_evidence> [session_id]"
        )

    visit_id = sys.argv[1].strip()
    claim = sys.argv[2].strip()
    exact_evidence = sys.argv[3]

    # session_id is accepted by the wrapper for a stable interface. The
    # observation itself determines which ledger receives the claim.
    session_id = sys.argv[4].strip() if len(sys.argv) > 4 else ""

    if not visit_id:
        fail("visit_id cannot be empty.")

    if not claim:
        fail("claim cannot be empty.")

    if not exact_evidence.strip():
        fail("exact_evidence cannot be empty.")

    entry, path, observation = find_observation(visit_id)

    rendered_text = observation.get("rendered_text")

    if not isinstance(rendered_text, str):
        fail(
            f"Browser observation {visit_id} has no usable "
            f"rendered_text field."
        )

    start = rendered_text.find(exact_evidence)

    if start == -1:
        fail(
            "DIRECT evidence rejected: exact_evidence does not occur "
            "verbatim in the stored browser observation. Copy the "
            "passage exactly from the source evidence and try again."
        )

    end = start + len(exact_evidence)

    claim_id = make_claim_id()
    recorded_at = utc_now()

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "claim_evidence",
        "claim_id": claim_id,
        "recorded_at_utc": recorded_at,
        "status": "DIRECT",
        "visit_id": visit_id,
        "claim": claim,
        "exact_evidence": exact_evidence,
        "evidence_start_char": start,
        "evidence_end_char": end,
        "evidence_sha256": hashlib.sha256(
            exact_evidence.encode("utf-8")
        ).hexdigest(),
        "source_url": observation.get("final_url")
            or observation.get("requested_url"),
        "source_title": observation.get("title", ""),
        "source_captured_at_utc": observation.get(
            "captured_at_utc"
        ),
    }

    append_record(path, record)
    ledger_common.bump_ledger_updated(entry)

    print(json.dumps(
        {
            "ok": True,
            "claim_id": claim_id,
            "status": "DIRECT",
            "visit_id": visit_id,
            "source_url": record["source_url"],
            "source_title": record["source_title"],
            "evidence_start_char": start,
            "evidence_end_char": end,
            "ledger_path": str(path),
            "ledger_id": entry.get("ledger_id"),
            "recorded_at_utc": recorded_at,
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
