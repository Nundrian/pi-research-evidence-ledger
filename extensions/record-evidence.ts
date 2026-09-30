import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(EXTENSION_DIR, "record-evidence.py");

const PYTHON =
  process.env.PI_RESEARCH_LEDGER_PYTHON?.trim() ||
  (existsSync("/opt/pi-venv/bin/python")
    ? "/opt/pi-venv/bin/python"
    : "python3");

function runEvidence(
  visitId: string,
  claim: string,
  exactEvidence: string,
  signal?: AbortSignal,
  sessionId = "",
): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      PYTHON,
      [SCRIPT, visitId, claim, exactEvidence, sessionId],
      {
        maxBuffer: 1024 * 1024,
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
              "record_evidence failed."
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

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "record_evidence",
    label: "Record Evidence",
    description:
      "Record a DIRECT factual claim against an immutable Research Browser visit. " +
      "The exact_evidence passage MUST occur verbatim in the stored rendered page text " +
      "for the supplied visit_id. The tool independently verifies the quotation before " +
      "writing anything to the evidence ledger. Never invent, paraphrase, repair, infer, " +
      "or combine text in exact_evidence. If the evidence is not verbatim, the tool rejects it.",

    parameters: Type.Object({
      visit_id: Type.String({
        description:
          "Visit ID returned by research_browser, for example visit-20260929T001054Z-912b2b7e",
      }),
      claim: Type.String({
        description:
          "The factual claim supported by the cited passage.",
      }),
      exact_evidence: Type.String({
        description:
          "A verbatim passage copied from the stored source evidence. It must match the browser observation exactly.",
      }),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const sessionId = ctx.sessionManager.getSessionId() ?? "";

      const raw = await runEvidence(
        params.visit_id,
        params.claim,
        params.exact_evidence,
        signal,
        sessionId
      );

      let result: any;
      try {
        result = JSON.parse(raw);
      } catch {
        throw new Error(
          `Record Evidence returned invalid output:\n${raw}`
        );
      }

      if (!result.ok) {
        throw new Error(
          result.error || "Evidence was rejected."
        );
      }

      const output = [
        "DIRECT EVIDENCE RECORDED",
        "------------------------",
        `Claim ID: ${result.claim_id}`,
        `Visit ID: ${result.visit_id}`,
        `Status: ${result.status}`,
        `Source title: ${result.source_title || "(none)"}`,
        `Source URL: ${result.source_url || "(none)"}`,
        `Evidence characters: ${result.evidence_start_char}–${result.evidence_end_char}`,
        `Ledger ID: ${result.ledger_id || "(none)"}`,
        `Ledger: ${result.ledger_path}`,
      ].join("\n");

      return {
        content: [{ type: "text", text: output }],
        details: result,
      };
    },
  });
}
