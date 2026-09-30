import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(EXTENSION_DIR, "evidence-lookup.py");

const PYTHON =
  process.env.PI_RESEARCH_LEDGER_PYTHON?.trim() ||
  (existsSync("/opt/pi-venv/bin/python")
    ? "/opt/pi-venv/bin/python"
    : "python3");

function runLookup(
  mode: string,
  query: string | undefined,
  limit: number,
  signal?: AbortSignal,
  sessionId = "",
  scope = "current",
): Promise<string> {
  return new Promise((resolve, reject) => {
    const args = [SCRIPT, mode];

    if (mode === "recent") {
      args.push(String(limit));
    } else if (query) {
      args.push(query);
    }

    args.push(sessionId);
    args.push(scope);

    const child = execFile(
      PYTHON,
      args,
      {
        maxBuffer: 4 * 1024 * 1024,
        timeout: 30000,
        signal,
      },
      (error, stdout, stderr) => {
        const out = stdout?.trim() || "";

        if (out) {
          resolve(out);
          return;
        }

        if (error) {
          reject(
            new Error(
              stderr?.trim() ||
              error.message ||
              "evidence_lookup failed."
            )
          );
          return;
        }

        resolve(out);
      }
    );

    child.on("error", reject);
  });
}

function formatClaim(claim: any): string {
  const errors = Array.isArray(claim.integrity_errors)
    ? claim.integrity_errors
    : [];

  return [
    `Claim ID: ${claim.claim_id || "(none)"}`,
    `Status: ${claim.status || "(none)"}`,
    `Claim: ${claim.claim || "(none)"}`,
    `Visit ID: ${claim.visit_id || "(none)"}`,
    `Integrity verified: ${claim.integrity_verified ? "yes" : "NO"}`,
    `Integrity errors: ${errors.length ? errors.join(" | ") : "none"}`,
    `Exact evidence: ${claim.exact_evidence || "(none)"}`,
    `Source title: ${claim.source_title || "(none)"}`,
    `Source URL: ${claim.source_url || "(none)"}`,
    `Ledger: ${claim._ledger_path || "(none)"}`,
    `Recorded UTC: ${claim.recorded_at_utc || "(none)"}`,
  ].join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "evidence_lookup",
    label: "Evidence Lookup",
    description:
      "Read verified factual evidence from the persistent research evidence ledger. " +
      "Use this to recover trusted evidence after context compaction or whenever a factual " +
      "claim, date, quotation, identifier, number, or source attribution needs verification. " +
      "This tool is read-only. It independently rechecks DIRECT claim evidence against the " +
      "stored browser observation and reports integrity_verified and any integrity errors. " +
      "By default it searches only the current research session ledger; scope='all' searches " +
      "all registered ledgers. Prefer integrity-verified ledger evidence over remembered or " +
      "compacted conversation summaries.",

    parameters: Type.Object({
      mode: Type.String({
        description: "Lookup mode: claim, visit, url, or recent.",
      }),
      query: Type.Optional(
        Type.String({
          description:
            "For claim: Claim ID. For visit: Visit ID. For url: exact source URL. Omit for recent.",
        })
      ),
      limit: Type.Optional(
        Type.Integer({
          minimum: 1,
          maximum: 100,
          description:
            "For recent mode only. Number of recent claims to return. Default 10.",
        })
      ),
      scope: Type.Optional(
        Type.String({
          description:
            'Lookup scope: "current" (default, current Pi session ledger only) or "all" (all registered ledgers).',
        })
      ),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const sessionId = ctx.sessionManager.getSessionId() ?? "";
      const mode = String(params.mode || "").trim().toLowerCase();

      const allowed = new Set(["claim", "visit", "url", "recent"]);
      if (!allowed.has(mode)) {
        throw new Error(
          "Invalid evidence_lookup mode. Use claim, visit, url, or recent."
        );
      }

      if (
        mode !== "recent" &&
        (!params.query || !String(params.query).trim())
      ) {
        throw new Error(
          `evidence_lookup mode "${mode}" requires query.`
        );
      }

      const scope = String(params.scope || "current")
        .trim()
        .toLowerCase();

      if (scope !== "current" && scope !== "all") {
        throw new Error(
          'Invalid evidence_lookup scope. Use "current" or "all".'
        );
      }

      const raw = await runLookup(
        mode,
        params.query ? String(params.query).trim() : undefined,
        params.limit ?? 10,
        signal,
        sessionId,
        scope
      );

      let result: any;
      try {
        result = JSON.parse(raw);
      } catch {
        throw new Error(
          `Evidence Lookup returned invalid output:\n${raw}`
        );
      }

      if (!result.ok) {
        throw new Error(
          result.error || "Evidence lookup failed."
        );
      }

      let body = "";

      if (mode === "claim") {
        body = [
          "VERIFIED CLAIM",
          "--------------",
          formatClaim(result.claim),
          "",
          "SOURCE OBSERVATION",
          "------------------",
          `Visit ID: ${result.observation?.visit_id || "(none)"}`,
          `Captured UTC: ${result.observation?.captured_at_utc || "(none)"}`,
          `Title: ${result.observation?.title || "(none)"}`,
          `URL: ${
            result.observation?.final_url ||
            result.observation?.requested_url ||
            "(none)"
          }`,
          `Ledger: ${result.observation?.ledger_path || "(none)"}`,
        ].join("\n");
      } else {
        const claims = Array.isArray(result.claims) ? result.claims : [];
        const formatted = claims.map(
          (claim: any, index: number) =>
            [
              `CLAIM ${index + 1}`,
              "-------",
              formatClaim(claim),
            ].join("\n")
        );

        const ledgerPaths = Array.isArray(result.ledger_paths)
          ? result.ledger_paths
          : [];

        body = [
          `EVIDENCE LOOKUP: ${mode.toUpperCase()}`,
          "-----------------------------",
          `Claims returned: ${claims.length}`,
          `Ledgers: ${ledgerPaths.length}`,
          ...ledgerPaths.map((p) => `  ${p}`),
          "",
          formatted.length
            ? formatted.join("\n\n")
            : "(No recorded claims found)",
        ].join("\n");
      }

      return {
        content: [{ type: "text", text: body }],
        details: result,
      };
    },
  });
}
