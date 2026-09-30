from pathlib import Path
import py_compile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions"


def test_python_sources_compile():
    for name in (
        "ledger_common.py",
        "research-browser.py",
        "record-evidence.py",
        "evidence-lookup.py",
    ):
        py_compile.compile(str(EXT / name), doraise=True)


def test_typescript_wrappers_do_not_hardcode_extension_home():
    for name in (
        "research-browser.ts",
        "record-evidence.ts",
        "evidence-lookup.ts",
    ):
        text = (EXT / name).read_text(encoding="utf-8")
        assert "/root/.pi/agent/extensions/" not in text
        assert "fileURLToPath(import.meta.url)" in text


def test_browser_path_is_configurable():
    text = (EXT / "research-browser.py").read_text(encoding="utf-8")
    assert "RESEARCH_BROWSER_CHROMIUM" in text
    assert 'browser_executable_path="/usr/bin/chromium"' not in text


def test_missing_ledger_guard_is_present():
    text = (EXT / "ledger_common.py").read_text(encoding="utf-8")
    assert "LEDGER_MISSING" in text
    assert "Refusing to create a replacement automatically" in text


def test_repository_does_not_ship_evidence_data():
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()

    forbidden_suffixes = {".jsonl", ".pyc"}
    assert not [
        path for path in tracked
        if Path(path).suffix in forbidden_suffixes
    ]
