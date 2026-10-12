# Security and privacy

This extension runs a real Chromium browser and stores source observations and factual evidence on disk. It is intended for **trusted users operating in a controlled Pi environment**, not as a security boundary between mutually untrusted people.

## Important trust boundaries

- **Untrusted webpages:** `research_browser` visits arbitrary HTTP/HTTPS URLs and executes page JavaScript in Chromium. The browser's network access may include localhost, private network services or other resources reachable from its container. Keep the browser in an isolated container/network with only the connectivity it needs; do not use an authenticated personal browser profile or mount secrets into the browser environment.
- **Prompt injection:** Text on a visited webpage, including hidden or adversarial instructions that appear in the rendered text, must be treated as untrusted evidence, not as instructions to the assistant. The ledger does not neutralise prompt injection.
- **Persistent evidence is sensitive:** The ledger stores rendered page text, URLs, observations and quotes. Use a dedicated restricted `RESEARCH_LEDGER_DIR`, appropriate filesystem permissions and backups; do not commit research ledgers to Git.
- **Session separation is not a security boundary:** Separate ledgers organise work by Pi session. `evidence_lookup` can deliberately search all registered ledgers using `scope="all"`, and `record_evidence` looks up a supplied visit ID across ledgers. This is **not suitable for untrusted multi-user deployments** without additional authorisation checks.
- **Evidence is not verification of a claim's truth:** Verbatim matching and SHA-256 detect some consistency errors, not fabricated source content, compromised sources or an attacker who can rewrite both the evidence file and its hashes.
- **Dependency drift:** `nodriver` is not version-pinned in `requirements.txt`, and Pi peer dependencies permit multiple versions. Reproducible deployments should pin reviewed dependency versions in their environment and test compatibility before upgrades. The included CI exercises offline tests, not live Chromium safety.

## Safer operation

1. Run Pi and Chromium in a dedicated unprivileged container or VM, with restricted network access and a narrow workspace mount.
2. Use only trusted user accounts for research sessions sharing the same ledger directory.
3. Avoid scanning authenticated intranet pages, localhost services and documents containing private information unless that is explicitly intended and authorised.
4. Review generated references and direct claims against the original source independently for high-stakes research.
5. Preserve ledgers and the registry together when backing up or restoring work.

## Reporting

Use a GitHub issue for non-sensitive questions or errors. Do not post credentials, private pages, a working exploit against a real target, or sensitive ledger data in a public issue. Ask the maintainer for a private reporting route if a vulnerability involves sensitive details.

This is a documented trust-boundary review, **not** an independent penetration test or malware scan.
