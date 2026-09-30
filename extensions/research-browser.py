#!/usr/bin/env python3

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import ledger_common

LEDGER_SCHEMA_VERSION = 1


def utc_now():
    return ledger_common.utc_now()


def make_visit_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"visit-{stamp}-{uuid4().hex[:8]}"


def _canned_observation(max_chars, max_links, url, ledger_path):
    visit_id = make_visit_id()
    captured_at = utc_now()
    full_text = (
        "Unit-test rendered page. The casino in Agadir opened in 2024 "
        "with an enchanted emerald facade and two hundred tables."
    )
    record = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "record_type": "browser_observation",
        "visit_id": visit_id,
        "captured_at_utc": captured_at,
        "requested_url": url,
        "final_url": url,
        "title": "Unit Test Page",
        "rendered_text": full_text,
        "text_characters": len(full_text),
        "metadata": {"language": "en"},
        "links": [],
        "links_observed": 0,
        "capture_method": {
            "browser": "Unit",
            "automation": "seam",
            "evidence_type": "canned",
        },
    }
    ledger_common.append_record_to_path(ledger_path, record)
    return {
        "ok": True,
        "visit_id": visit_id,
        "ledger_path": str(ledger_path),
        "captured_at_utc": captured_at,
        "title": "Unit Test Page",
        "url": url,
        "text": full_text[:max_chars],
        "truncated": len(full_text) > max_chars,
        "characters": len(full_text),
        "metadata": {"language": "en"},
        "links": [],
        "links_returned": 0,
        "links_observed": 0,
    }


def resolve_browser_executable():
    configured = os.environ.get("RESEARCH_BROWSER_CHROMIUM", "").strip()

    if configured:
        candidate = Path(configured).expanduser()
        if candidate.exists():
            return str(candidate)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise FileNotFoundError(
            "RESEARCH_BROWSER_CHROMIUM is set but the executable was not "
            f"found: {configured!r}"
        )

    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
    ):
        resolved = shutil.which(name)
        if resolved:
            return resolved

    raise FileNotFoundError(
        "No compatible Chromium/Chrome executable was found. Install Chromium "
        "or Chrome, or set RESEARCH_BROWSER_CHROMIUM."
    )


_LINK_SCRIPT = r"""
JSON.stringify((() => {
  const clean = (v) => (v || "").replace(/\s+/g, " ").trim();

  const linkInfo = (a) => a ? {
    text: clean(a.innerText || a.textContent ||
                a.getAttribute("aria-label") || a.getAttribute("title")),
    url: a.href || ""
  } : null;

  const area = (a) => {
    if (a.closest("nav")) return "navigation";
    if (a.closest("header")) return "header";
    if (a.closest("footer")) return "footer";
    if (a.closest("aside")) return "aside";
    if (a.closest("main,article")) return "main";
    return "page";
  };

  const section = (a) => {
    const root = a.closest("section,article,main") || document.body;
    const headings = [...root.querySelectorAll("h1,h2,h3,h4,h5,h6")];
    let result = "";
    for (const h of headings) {
      if (h.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)
        result = clean(h.innerText || h.textContent);
    }
    return result;
  };

  const groupFor = (a) =>
    a.closest("ul,ol,dl,nav,aside,footer,header,section,article,main") ||
    a.parentElement;

  const groupLabel = (g) => {
    if (!g) return "";
    const aria = clean(g.getAttribute?.("aria-label"));
    if (aria) return aria;
    const labelledBy = g.getAttribute?.("aria-labelledby");
    if (labelledBy) {
      const el = document.getElementById(labelledBy);
      const txt = clean(el?.innerText || el?.textContent);
      if (txt) return txt;
    }
    const h = g.querySelector?.("h1,h2,h3,h4,h5,h6,legend");
    return clean(h?.innerText || h?.textContent);
  };

  return [...document.querySelectorAll("a[href]")].map((a) => {
    const g = groupFor(a);
    const links = g ? [...g.querySelectorAll("a[href]")] : [a];
    const i = links.indexOf(a);
    const block = a.closest("p,li,dd,dt,blockquote,figcaption,td,th") ||
                  a.parentElement;
    return {
      text: clean(a.innerText || a.textContent ||
                  a.getAttribute("aria-label") || a.getAttribute("title")),
      url: a.href || "",
      area: area(a),
      section: section(a),
      block_text: clean(block?.innerText || block?.textContent).slice(0, 1200),
      local_group_label: groupLabel(g),
      local_group_position: i >= 0 ? i + 1 : null,
      local_group_count: links.length,
      previous_link: i > 0 ? linkInfo(links[i - 1]) : null,
      next_link: i >= 0 && i < links.length - 1 ? linkInfo(links[i + 1]) : null
    };
  });
})())
"""


_METADATA_SCRIPT = r"""
JSON.stringify((() => {
  const meta = (name) => {
    const el = document.querySelector(
      `meta[name="${name}"],meta[property="${name}"]`
    );
    return el?.content?.trim() || "";
  };
  return {
    language: document.documentElement.lang || "",
    description: meta("description") || meta("og:description"),
    canonical_url: document.querySelector('link[rel="canonical"]')?.href || "",
    author: meta("author"),
    published_time:
      meta("article:published_time") || meta("datePublished") || meta("date"),
    modified_time:
      meta("article:modified_time") || meta("dateModified") ||
      meta("last-modified"),
    headings: [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
      .slice(0, 100)
      .map(h => ({
        level: h.tagName.toLowerCase(),
        text: (h.innerText || h.textContent || "").trim()
      }))
      .filter(h => h.text),
    time_elements: [...document.querySelectorAll("time")]
      .slice(0, 50)
      .map(t => ({
        datetime: t.getAttribute("datetime") || "",
        text: (t.innerText || t.textContent || "").trim()
      }))
      .filter(t => t.datetime || t.text)
  };
})())
"""


async def browse(url, max_chars, max_links, ledger_path):
    if os.environ.get("RESEARCH_BROWSER_UNIT") == "1":
        return _canned_observation(max_chars, max_links, url, ledger_path)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are allowed.")

    import nodriver as uc

    browser = None
    try:
        browser_executable = resolve_browser_executable()
        browser = await uc.start(
            headless=True,
            browser_executable_path=browser_executable,
        )

        page = await browser.get(url)
        await page.sleep(2)

        title = await page.evaluate("document.title") or ""
        final_url = await page.evaluate("window.location.href") or url
        full_text = await page.evaluate(
            "document.body ? document.body.innerText : ''"
        ) or ""

        try:
            links = json.loads(await page.evaluate(_LINK_SCRIPT) or "[]")
        except Exception:
            links = []

        try:
            metadata = json.loads(
                await page.evaluate(_METADATA_SCRIPT) or "{}"
            )
        except Exception:
            metadata = {}

        unique_links = []
        seen = set()
        for item in links:
            href = str(item.get("url", "")).strip()
            if not href or href in seen:
                continue
            if urlparse(href).scheme not in ("http", "https"):
                continue
            seen.add(href)
            unique_links.append(item)

        visit_id = make_visit_id()
        captured_at = utc_now()

        record = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "record_type": "browser_observation",
            "visit_id": visit_id,
            "captured_at_utc": captured_at,
            "requested_url": url,
            "final_url": final_url,
            "title": title,
            "rendered_text": full_text,
            "text_characters": len(full_text),
            "metadata": metadata,
            "links": unique_links,
            "links_observed": len(unique_links),
            "capture_method": {
                "browser": Path(browser_executable).name,
                "automation": "Nodriver",
                "evidence_type": "rendered_dom",
            },
        }

        ledger_common.append_record_to_path(ledger_path, record)

        returned_links = unique_links[:max_links]
        return {
            "ok": True,
            "visit_id": visit_id,
            "ledger_path": str(ledger_path),
            "captured_at_utc": captured_at,
            "title": title,
            "url": final_url,
            "text": full_text[:max_chars],
            "truncated": len(full_text) > max_chars,
            "characters": len(full_text),
            "metadata": metadata,
            "links": returned_links,
            "links_returned": len(returned_links),
            "links_observed": len(unique_links),
        }
    finally:
        if browser is not None:
            browser.stop()


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "URL argument required"}))
        raise SystemExit(1)

    url = sys.argv[1]
    max_chars = int(sys.argv[2]) if len(sys.argv) > 2 else 15000
    max_links = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    session_id = sys.argv[4] if len(sys.argv) > 4 else ""
    topic = sys.argv[5] if len(sys.argv) > 5 else ""

    max_chars = max(1000, min(max_chars, 50000))
    max_links = max(1, min(max_links, 500))

    try:
        entry, ledger_path = ledger_common.resolve_ledger_for_session(
            session_id, topic
        )
        result = await browse(url, max_chars, max_links, ledger_path)
        result["ledger_id"] = entry["ledger_id"]
        result["session_id"] = session_id
        result["topic"] = entry.get("topic") or ""
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    if os.environ.get("RESEARCH_BROWSER_UNIT") == "1":
        asyncio.run(main())
    else:
        import nodriver as uc
        uc.loop().run_until_complete(main())
