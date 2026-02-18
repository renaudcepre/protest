"""Generate terminal output snippets for the documentation.

Reads doc-examples.yml, runs each command, captures ANSI-colored output,
and writes to website/public/_outputs/{id}.ansi.

Usage:
    python scripts/generate-doc-outputs.py --update        # Regenerate all
    python scripts/generate-doc-outputs.py --only quickstart  # Just one
    python scripts/generate-doc-outputs.py --check         # Verify outputs match (CI)
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "doc-examples.yml"
OUTPUT_DIR = ROOT / "website" / "public" / "_outputs"


def load_manifest() -> list[dict]:
    with MANIFEST.open() as f:
        data = yaml.safe_load(f)
    return data["outputs"]


def _strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def clean_ansi_live_display(raw: str) -> str:
    """Strip Rich Live display artifacts from captured output.

    Rich Live uses cursor hide/show and carriage-return + erase-line sequences
    to render its status bar. We strip those to keep only the real output lines.
    """
    # Remove cursor hide/show
    text = raw.replace("\x1b[?25l", "").replace("\x1b[?25h", "")

    # Remove "move up N lines" sequences
    text = re.sub(r"\x1b\[\d*A", "", text)

    # Process carriage returns: for each line, only keep content after last \r\x1b[2K
    # (Rich writes "status_line\r\x1b[2K real_content")
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # Split on \r\x1b[2K and keep the last segment
        parts = re.split(r"\r\x1b\[2K", line)
        cleaned_line = parts[-1]
        # Also handle bare \r (without \x1b[2K)
        if "\r" in cleaned_line:
            cleaned_line = cleaned_line.rsplit("\r", 1)[-1]
        cleaned.append(cleaned_line)

    # Remove Rich Live residual lines (status bar that wasn't overwritten)
    final = []
    for line in cleaned:
        plain = _strip_ansi(line)
        # Skip Rich Live status lines ("⋯ RUNNING │ ..." or similar)
        if "RUNNING" in plain and "│" in plain:
            continue
        # Skip "Full output: .protest/..." lines
        if plain.strip().startswith("Full output:"):
            continue
        final.append(line)

    return "\n".join(final)


def normalize_durations(text: str) -> str:
    """Replace variable durations with stable placeholders for --check mode."""
    # Match patterns like "6ms", "12ms", "<1ms", "0.03s", "1.25s"
    text = re.sub(r"<1ms", "X.XXs", text)
    text = re.sub(r"\d+ms", "X.XXs", text)
    text = re.sub(r"\d+\.\d+s", "X.XXs", text)
    return text


def run_example(entry: dict) -> str:
    """Run a single example and return cleaned ANSI output."""
    working_dir = ROOT / entry["working_dir"]
    command = entry["command"]

    # Clean .protest cache before run
    protest_cache = working_dir / ".protest"
    if protest_cache.exists():
        shutil.rmtree(protest_cache)

    env = {
        "FORCE_COLOR": "1",
        "COLUMNS": "120",
        "PATH": subprocess.check_output(  # noqa: S603 - trusted command
            ["bash", "-lc", "echo $PATH"],  # noqa: S607 - trusted command
        )
        .decode()
        .strip(),
        "HOME": str(Path.home()),
        "VIRTUAL_ENV": str(ROOT / ".venv"),
    }

    result = subprocess.run(  # noqa: S603 - trusted commands from manifest
        ["uv", "run"] + command.split(),  # noqa: S607 - uv is a trusted tool
        cwd=working_dir,
        capture_output=True,
        env=env,
        timeout=30,
    )

    if not entry.get("expect_failure", False) and result.returncode != 0:
        print(f"  WARNING: '{command}' exited with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr.decode()[:500]}")

    raw = result.stdout.decode("utf-8", errors="replace")
    if result.stderr:
        raw += result.stderr.decode("utf-8", errors="replace")

    return clean_ansi_live_display(raw)


def update(only: str | None = None) -> None:
    """Regenerate output files."""
    entries = load_manifest()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        entry_id = entry["id"]
        if only and entry_id != only:
            continue

        print(f"  Generating {entry_id}...")
        output = run_example(entry)
        output_file = OUTPUT_DIR / f"{entry_id}.ansi"
        output_file.write_text(output)
        print(f"  -> {output_file.relative_to(ROOT)} ({len(output)} bytes)")

        # Copy source file if specified
        source_file = entry.get("source_file")
        if source_file:
            src = ROOT / entry["working_dir"] / source_file
            sources_dir = OUTPUT_DIR / "sources"
            sources_dir.mkdir(exist_ok=True)
            dst = sources_dir / source_file
            if not dst.exists() or src.read_text() != dst.read_text():
                shutil.copy2(src, dst)
                print(f"  -> {dst.relative_to(ROOT)} (source)")

    print("Done.")


def check() -> bool:
    """Verify that committed outputs match a fresh run."""
    entries = load_manifest()
    all_ok = True

    for entry in entries:
        entry_id = entry["id"]
        output_file = OUTPUT_DIR / f"{entry_id}.ansi"

        if not output_file.exists():
            print(f"  MISSING: {output_file.relative_to(ROOT)}")
            all_ok = False
            continue

        print(f"  Checking {entry_id}...")
        fresh = run_example(entry)
        existing = output_file.read_text()

        # Normalize durations before comparing
        if normalize_durations(fresh) != normalize_durations(existing):
            print(f"  MISMATCH: {entry_id}")
            all_ok = False
        else:
            print(f"  OK: {entry_id}")

    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate doc output snippets")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--update", action="store_true", help="Regenerate outputs")
    group.add_argument("--check", action="store_true", help="Verify outputs match")
    parser.add_argument("--only", help="Only process this entry id")

    args = parser.parse_args()

    if args.update:
        update(only=args.only)
    elif args.check:
        if not check():
            print("\nOutputs are stale! Run: python scripts/generate-doc-outputs.py --update")
            sys.exit(1)
        print("\nAll outputs up to date.")


if __name__ == "__main__":
    main()
