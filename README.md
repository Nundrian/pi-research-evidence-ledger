# Pi Research Evidence Ledger

Persistent, append-only research evidence provenance for long-running [Pi](https://github.com/earendil-works/pi) sessions.

The extension stores browser observations and verified claims outside conversational context so a research session can recover source-backed evidence after context compaction instead of relying only on a generated summary.

## Why this exists

Long research sessions can survive compaction while still losing fine factual distinctions. Two correct observations can be compressed into one unsupported claim. The ledger preserves the original observation, exact supporting passage, source URL, capture time, character offsets, and SHA-256 so later lookups can re-verify the claim against the stored observation.

This is **not a replacement for Pi memory or compaction**. It is an evidence/provenance layer.

## What it provides

Three Pi tools are installed:

- `research_browser` — renders a page through Chromium/Nodriver and writes an immutable browser observation to the current session ledger.
- `record_evidence` — records a DIRECT claim only when the supplied evidence occurs verbatim in the stored observation.
- `evidence_lookup` — reloads claims and independently verifies verbatim evidence, offsets, source URL, and SHA-256.

Each Pi session gets a separate human-readable JSONL ledger under `RESEARCH_LEDGER_DIR`. A durable `index.json` maps the stable Pi session ID to its ledger, so the same session reuses the same evidence store after compaction.

## Safety properties

- append-only JSONL evidence records
- one ledger per Pi session/run
- collision-safe human-readable filenames
- atomic registry updates
- file locking around concurrent writes and registry mutation
- legacy single-ledger discovery without inventing metadata
- DIRECT claims require verbatim source text
- SHA-256 integrity check on recorded evidence
- missing registered ledgers fail with `LEDGER_MISSING` rather than silently creating a replacement
- current-session lookup is the Pi tool default; explicit `scope="all"` searches across registered ledgers

## Requirements

- Pi with package support
- Python 3.11+
- [`nodriver`](https://github.com/ultrafunkamsterdam/nodriver)
- Chromium or Google Chrome available to the Pi host/container
- POSIX file locking (`fcntl`): Linux/macOS are supported; on Windows use WSL/containerised Pi for this v0.1.0 candidate

Install the Python browser dependency into the Python environment used by Pi:

```bash
python3 -m pip install nodriver
```

If Pi uses a dedicated virtual environment, set `PI_RESEARCH_LEDGER_PYTHON` to that interpreter.

## Install from GitHub

```bash
pi install git:github.com/Nundrian/pi-research-evidence-ledger
```

Then use `/reload` or start a new Pi session.

Pi packages can expose extensions from the conventional `extensions/` directory or through the `pi.extensions` manifest; this package explicitly declares the three TypeScript entry points.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `RESEARCH_LEDGER_DIR` | Per-run ledgers and `index.json` | `/workspace/research/ledgers` |
| `RESEARCH_LEGACY_LEDGER` | Existing pre-upgrade single ledger | `/workspace/research/evidence-ledger.jsonl` |
| `RESEARCH_BROWSER_CHROMIUM` | Chromium/Chrome executable or command name | auto-discovered |
| `PI_RESEARCH_LEDGER_PYTHON` | Python interpreter used by the TypeScript wrappers | `/opt/pi-venv/bin/python` if present, otherwise `python3` |

The browser resolver searches `chromium`, `chromium-browser`, `google-chrome`, and `google-chrome-stable` when no override is supplied.

## Typical workflow

1. Research with `research_browser`.
2. When a source directly supports a factual claim, call `record_evidence` with the returned `visit_id`, the claim, and an exact verbatim passage.
3. After compaction, or before relying on a sensitive detail, call `evidence_lookup`.
4. Prefer integrity-verified ledger evidence over a conflicting compacted summary.

### Lookup scopes

`evidence_lookup` defaults to the current Pi session ledger.

Use `scope="all"` deliberately when you want to search across research runs, including the legacy ledger.

## Storage layout

```text
/workspace/research/
├── evidence-ledger.jsonl        # optional legacy ledger, preserved
└── ledgers/
    ├── index.json
    ├── 2026-09-29_topic-a.jsonl
    └── 2026-09-29_topic-b.jsonl
```

Actual research ledgers are data, not package source, and must not be committed to Git.

## Tests

Python tests use a deterministic browser seam and do not launch Chromium:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

A dependency-free TypeScript syntax check is available on Node 22+:

```bash
npm run check:ts-syntax
```

For full TypeScript type checking, install development dependencies and run:

```bash
npm install
npm run typecheck
```

The test suite covers session isolation, compaction-safe resolution, concurrent creation, collision handling, legacy preservation, verbatim evidence enforcement, integrity verification, cross-ledger lookup, current/all lookup scopes, and safe failure when a registered ledger file is missing.

## Project status

`v0.1.0` is the first public-package candidate. It originated as part of a long-running Pi research workflow and has been separated into a standalone package for broader testing.

## Licence

A public open-source licence has not yet been selected. Do not treat the current staging version as licensed for redistribution until a licence is added.
