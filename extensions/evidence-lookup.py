#!/usr/bin/env python3

import sys
import json
import fcntl
import hashlib
from pathlib import Path

import ledger_common


def output(data, exit_code=0):
    print(json.dumps(data, ensure_ascii=False))
    sys.exit(exit_code)


def fail(message):
    output(
        {
            "ok": False,
            "error": message,
        },
        1,
    )


def load_all_records(scope="all", session_id=""):
    """Load records from registered ledgers.

    scope="current" restricts lookup to the ledger mapped to session_id.
    scope="all" searches every registered ledger, including the legacy ledger.

    Each record is annotated with its source ledger path and line number.
    A missing current-session ledger is treated as an explicit continuity
    error rather than being silently replaced.
    """
    entries = ledger_common.all_ledger_entries()

    if scope == "current":
        sid = str(session_id or "").strip()
        if not sid:
            fail("Current-ledger lookup requires a non-empty session_id.")

        entries = [
            entry
            for entry in entries
            if not entry.get("legacy")
            and entry.get("session_id") == sid
        ]

        if not entries:
            fail(
                "No evidence ledger is registered for the current session. "
                "Use research_browser first, or use scope='all' to search "
                "existing ledgers."
            )

        for entry in entries:
            path = Path(entry.get("path", ""))
            if not path.exists():
                fail(
                    "LEDGER_MISSING: the current session is registered to "
                    f"{str(path)!r}, but that file is missing."
                )

    records = []

    for entry in entries:
        path = Path(entry.get("path", ""))
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)

            try:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        fail(
                            f"Invalid JSON in {path} at line "
                            f"{line_number}: {exc}"
                        )

                    record["_ledger_path"] = str(path)
                    record["_ledger_line"] = line_number
                    records.append(record)

            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    return records


def build_indexes(records):
    observations = {}
    claims = []

    for record in records:
        record_type = record.get("record_type")

        if record_type == "browser_observation":
            visit_id = record.get("visit_id")

            if visit_id and visit_id not in observations:
                observations[visit_id] = record

        elif record_type == "claim_evidence":
            claims.append(record)

    ledger_paths = sorted(
        {
            r.get("_ledger_path")
            for r in records
            if r.get("_ledger_path")
        }
    )

    return observations, claims, ledger_paths


def verify_claim(claim, observations):
    result = dict(claim)

    visit_id = claim.get("visit_id")
    observation = observations.get(visit_id)

    errors = []

    if observation is None:
        errors.append(
            f"Referenced browser observation not found: {visit_id}"
        )
    else:
        rendered_text = observation.get("rendered_text")
        exact_evidence = claim.get("exact_evidence")

        if not isinstance(rendered_text, str):
            errors.append(
                "Referenced browser observation has no usable rendered_text."
            )

        elif not isinstance(exact_evidence, str):
            errors.append(
                "Claim has no usable exact_evidence."
            )

        else:
            expected_start = claim.get("evidence_start_char")
            expected_end = claim.get("evidence_end_char")

            actual_start = rendered_text.find(exact_evidence)

            if actual_start == -1:
                errors.append(
                    "exact_evidence no longer occurs verbatim in the "
                    "referenced browser observation."
                )
            else:
                actual_end = actual_start + len(exact_evidence)

                if (
                    expected_start is not None
                    and expected_start != actual_start
                ):
                    errors.append(
                        f"Evidence start offset mismatch: stored "
                        f"{expected_start}, actual {actual_start}."
                    )

                if (
                    expected_end is not None
                    and expected_end != actual_end
                ):
                    errors.append(
                        f"Evidence end offset mismatch: stored "
                        f"{expected_end}, actual {actual_end}."
                    )

            stored_hash = claim.get("evidence_sha256")

            if stored_hash:
                actual_hash = hashlib.sha256(
                    exact_evidence.encode("utf-8")
                ).hexdigest()

                if stored_hash != actual_hash:
                    errors.append(
                        "Evidence SHA-256 mismatch."
                    )

        source_url = (
            observation.get("final_url")
            or observation.get("requested_url")
        )

        if (
            claim.get("source_url")
            and source_url
            and claim.get("source_url") != source_url
        ):
            errors.append(
                "Stored claim source URL does not match the referenced "
                "browser observation."
            )

    result["integrity_verified"] = len(errors) == 0
    result["integrity_errors"] = errors

    return result


def observation_summary(observation):
    if observation is None:
        return None

    return {
        "visit_id": observation.get("visit_id"),
        "captured_at_utc": observation.get("captured_at_utc"),
        "requested_url": observation.get("requested_url"),
        "final_url": observation.get("final_url"),
        "title": observation.get("title"),
        "text_characters": observation.get("text_characters"),
        "links_observed": observation.get("links_observed"),
        "capture_method": observation.get("capture_method"),
        "ledger_line": observation.get("_ledger_line"),
        "ledger_path": observation.get("_ledger_path"),
    }


def recent_key(claim):
    ts = claim.get("recorded_at_utc") or ""
    return (
        1 if ts else 0,
        ts,
        claim.get("_ledger_path") or "",
        claim.get("claim_id") or "",
    )


def main():
    if len(sys.argv) < 2:
        fail(
            "Usage: evidence-lookup.py "
            "claim <claim_id> | "
            "visit <visit_id> | "
            "url <source_url> | "
            "recent [limit] [session_id] [scope]"
        )

    mode = sys.argv[1].strip().lower()

    session_id = sys.argv[3].strip() if len(sys.argv) > 3 else ""
    scope = sys.argv[4].strip().lower() if len(sys.argv) > 4 else "all"

    if scope not in ("current", "all"):
        fail('scope must be "current" or "all".')

    records = load_all_records(scope=scope, session_id=session_id)
    observations, claims, ledger_paths = build_indexes(records)

    if mode == "claim":
        if len(sys.argv) < 3 or len(sys.argv) > 5:
            fail("Usage: evidence-lookup.py claim <claim_id>")

        claim_id = sys.argv[2].strip()

        for claim in claims:
            if claim.get("claim_id") == claim_id:
                verified = verify_claim(claim, observations)

                output(
                    {
                        "ok": True,
                        "mode": "claim",
                        "ledger_paths": ledger_paths,
                        "claim": verified,
                        "observation": observation_summary(
                            observations.get(claim.get("visit_id"))
                        ),
                    }
                )

        fail(f"Claim ID not found: {claim_id}")

    elif mode == "visit":
        if len(sys.argv) < 3 or len(sys.argv) > 5:
            fail("Usage: evidence-lookup.py visit <visit_id>")

        visit_id = sys.argv[2].strip()
        observation = observations.get(visit_id)

        if observation is None:
            fail(f"Visit ID not found: {visit_id}")

        matching_claims = [
            verify_claim(claim, observations)
            for claim in claims
            if claim.get("visit_id") == visit_id
        ]

        output(
            {
                "ok": True,
                "mode": "visit",
                "ledger_paths": ledger_paths,
                "observation": observation_summary(observation),
                "claims": matching_claims,
                "claim_count": len(matching_claims),
            }
        )

    elif mode == "url":
        if len(sys.argv) < 3 or len(sys.argv) > 5:
            fail("Usage: evidence-lookup.py url <source_url>")

        source_url = sys.argv[2].strip()

        matching_claims = [
            verify_claim(claim, observations)
            for claim in claims
            if claim.get("source_url") == source_url
        ]

        matching_visits = []

        for observation in observations.values():
            observation_url = (
                observation.get("final_url")
                or observation.get("requested_url")
            )

            if observation_url == source_url:
                matching_visits.append(
                    observation_summary(observation)
                )

        output(
            {
                "ok": True,
                "mode": "url",
                "ledger_paths": ledger_paths,
                "source_url": source_url,
                "visits": matching_visits,
                "claims": matching_claims,
                "claim_count": len(matching_claims),
            }
        )

    elif mode == "recent":
        limit = 10

        if len(sys.argv) >= 3 and sys.argv[2].strip():
            try:
                limit = int(sys.argv[2])
            except ValueError:
                fail("recent limit must be an integer.")

        if limit < 1 or limit > 100:
            fail("recent limit must be between 1 and 100.")

        recent_claims = sorted(claims, key=recent_key, reverse=True)

        verified = [
            verify_claim(claim, observations)
            for claim in recent_claims[:limit]
        ]

        output(
            {
                "ok": True,
                "mode": "recent",
                "ledger_paths": ledger_paths,
                "claims": verified,
                "claim_count": len(verified),
            }
        )

    else:
        fail(
            f"Unknown lookup mode: {mode}. "
            f"Use claim, visit, url, or recent."
        )


if __name__ == "__main__":
    main()
