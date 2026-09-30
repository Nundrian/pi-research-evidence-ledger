import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(EXTENSION_DIR, "research-browser.py");

const PYTHON =
  process.env.PI_RESEARCH_LEDGER_PYTHON?.trim() ||
  (existsSync("/opt/pi-venv/bin/python")
    ? "/opt/pi-venv/bin/python"
    : "python3");

const ledgersAnnounced = new Set<string>();

function runBrowser(
  url: string,
  maxChars: number,
  maxLinks: number,
  signal?: AbortSignal,
  sessionId = "",
  topic = "",
): Promise<string> {
  return new Promise((resolve, reject) => {
    const args = [
      SCRIPT,
      url,
      String(maxChars),
      String(maxLinks),
      sessionId,
      topic,
    ];

    const child = execFile(
      PYTHON,
      args,
      {
        maxBuffer: 1024 * 1024,
        timeout: 60000,
        signal,
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(
            new Error(
              stderr?.trim() ||
              stdout?.trim() ||
              error.message
            )
          );
          return;
        }

        resolve(stdout.trim());
      }
    );

    child.on("error", reject);
  });
}

function formatNeighbour(label: string, link: any): string {
  if (!link) return `${label}: none`;

  return [
    `${label}: ${link.text || "(no link text)"}`,
    `${label} URL: ${link.url || "(none)"}`,
  ].join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "research_browser",
    label: "Research Browser",
    description:
      "Open an HTTP or HTTPS webpage in a real Chromium browser using Nodriver. " +
      "Use this for JavaScript-rendered pages, dynamic research pages, and compatible " +
      "Cloudflare or anti-bot protected pages. Returns rendered text, metadata, headings, " +
      "dates, and DOM-grounded link evidence including area, section, exact enclosing block, " +
      "local group position, previous link and next link. IMPORTANT: when reporting page " +
      "structure, adjacency or surrounding context, rely on the supplied evidence fields. " +
      "Do not invent or infer relationships that are not explicitly present in the tool output.",

    parameters: Type.Object({
      url: Type.String({
        description: "Full http:// or https:// URL to open",
      }),
      max_chars: Type.Optional(
        Type.Integer({
          minimum: 1000,
          maximum: 50000,
          description:
            "Maximum rendered text characters to return. Default 15000.",
        })
      ),
      max_links: Type.Optional(
        Type.Integer({
          minimum: 1,
          maximum: 500,
          description:
            "Maximum number of unique HTTP/HTTPS links to return. Default 100.",
        })
      ),
      topic: Type.Optional(
        Type.String({
          description:
            "Research topic for this session. The first browse for a session " +
            "creates a per-run ledger file named YYYY-MM-DD_<topic-slug>.jsonl; " +
            "later calls (including after compaction) reuse the same ledger. " +
            "If omitted, the session display name is used.",
        })
      ),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const maxChars = params.max_chars ?? 15000;
      const maxLinks = params.max_links ?? 100;

      const sessionManager = ctx.sessionManager;
      const sessionId = sessionManager.getSessionId() ?? "";
      const sessionName = sessionManager.getSessionName() ?? "";
      const topic = params.topic || sessionName || "";

      const raw = await runBrowser(
        params.url,
        maxChars,
        maxLinks,
        signal,
        sessionId,
        topic
      );

      let result: any;
      try {
        result = JSON.parse(raw);
      } catch {
        throw new Error(
          `Research Browser returned invalid output:\n${raw}`
        );
      }

      if (!result.ok) {
        throw new Error(
          result.error || "Research Browser failed."
        );
      }

      if (sessionId && !ledgersAnnounced.has(sessionId)) {
        ledgersAnnounced.add(sessionId);
        pi.appendEntry("ledger_state", {
          session_id: sessionId,
          ledger_id: result.ledger_id,
          ledger_path: result.ledger_path,
          topic: result.topic,
        });
      }

      const links = Array.isArray(result.links) ? result.links : [];
      const metadata = result.metadata || {};
      const headings = Array.isArray(metadata.headings)
        ? metadata.headings
        : [];
      const times = Array.isArray(metadata.time_elements)
        ? metadata.time_elements
        : [];

      const headingLines = headings.map(
        (heading: any, index: number) =>
          `[${index + 1}] ${String(heading.level || "").toUpperCase()} — ${heading.text}`
      );

      const timeLines = times.map(
        (item: any, index: number) =>
          `[${index + 1}] ${item.datetime || "(no datetime)"} — ${item.text || "(no visible text)"}`
      );

      const linkLines = links.map(
        (link: any, index: number) => {
          const parts = [
            `[${index + 1}] ${link.text || "(no link text)"}`,
            `URL: ${link.url}`,
            `Area: ${link.area || "page"}`,
            `Section: ${link.section || "(none)"}`,
            `Exact block text: ${link.block_text || "(none)"}`,
            `Local group label: ${link.local_group_label || "(none)"}`,
            `Local group position: ${link.local_group_position ?? "(unknown)"} of ${link.local_group_count ?? "(unknown)"}`,
            formatNeighbour("Previous link", link.previous_link),
            formatNeighbour("Next link", link.next_link),
          ];

          return parts.join("\n");
        }
      );

      const output = [
        `Visit ID: ${result.visit_id}`,
        `Evidence ledger: ${result.ledger_path}`,
        `Ledger ID: ${result.ledger_id || "(none)"}`,
        `Session: ${result.session_id || "(none)"}`,
        `Topic: ${result.topic || "(none)"}`,
        `Captured UTC: ${result.captured_at_utc}`,
        `Title: ${result.title}`,
        `URL: ${result.url}`,
        `Characters on page: ${result.characters}`,
        `Text truncated: ${result.truncated ? "yes" : "no"}`,
        `Links returned: ${result.links_returned ?? links.length}`,
        "",
        "EVIDENCE RULES",
        "--------------",
        "Area, section, exact block text, group position, previous link and next link are extracted from the rendered DOM.",
        "Do not claim structural relationships, neighbouring links or surrounding context unless supported by these fields or by explicit page text.",
        "",
        "METADATA",
        "--------",
        `Language: ${metadata.language || "(not exposed)"}`,
        `Description: ${metadata.description || "(not exposed)"}`,
        `Canonical URL: ${metadata.canonical_url || "(not exposed)"}`,
        `Author: ${metadata.author || "(not exposed)"}`,
        `Published: ${metadata.published_time || "(not exposed)"}`,
        `Modified: ${metadata.modified_time || "(not exposed)"}`,
        "",
        "HEADINGS",
        "--------",
        headingLines.length ? headingLines.join("\n") : "(No headings found)",
        "",
        "TIME ELEMENTS",
        "-------------",
        timeLines.length ? timeLines.join("\n") : "(No time elements found)",
        "",
        "PAGE TEXT",
        "---------",
        result.text,
        "",
        "LINK EVIDENCE",
        "-------------",
        linkLines.length ? linkLines.join("\n\n") : "(No HTTP/HTTPS links found)",
      ].join("\n");

      return {
        content: [{ type: "text", text: output }],
        details: {
          visit_id: result.visit_id,
          ledger_id: result.ledger_id,
          ledger_path: result.ledger_path,
          session_id: result.session_id,
          topic: result.topic,
          captured_at_utc: result.captured_at_utc,
          url: result.url,
          title: result.title,
          characters: result.characters,
          truncated: result.truncated,
          metadata,
          links,
        },
      };
    },
  });
}
