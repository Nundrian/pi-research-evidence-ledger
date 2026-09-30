import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions"
PYTHON = sys.executable

CANNED_TEXT = (
    "Unit-test rendered page. The casino in Agadir opened in 2024 "
    "with an enchanted emerald facade and two hundred tables."
)


def env_for(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(EXT)
    env["RESEARCH_LEDGER_DIR"] = str(tmp_path / "ledgers")
    env["RESEARCH_LEGACY_LEDGER"] = str(tmp_path / "evidence-ledger.jsonl")
    env["RESEARCH_BROWSER_UNIT"] = "1"
    return env


def run(script, *args, env):
    proc = subprocess.run(
        [PYTHON, str(EXT / script), *map(str, args)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    out = proc.stdout.strip()
    data = json.loads(out) if out else {}
    return proc.returncode, data, proc.stderr


def browse(url, session_id, topic, env):
    return run(
        "research-browser.py",
        url,
        "15000",
        "100",
        session_id,
        topic,
        env=env,
    )


def record(visit_id, claim, evidence, session_id, env):
    return run(
        "record-evidence.py",
        visit_id,
        claim,
        evidence,
        session_id,
        env=env,
    )


def lookup(mode, query="", session_id="", scope="all", env=None):
    if mode == "recent":
        return run(
            "evidence-lookup.py",
            mode,
            query or "10",
            session_id,
            scope,
            env=env,
        )
    return run(
        "evidence-lookup.py",
        mode,
        query,
        session_id,
        scope,
        env=env,
    )
