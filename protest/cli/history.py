"""CLI command: protest history — browse run history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from protest.history.storage import clean_dirty, load_history


def handle_history_command(argv: list[str]) -> None:
    """Entry point for `protest history`."""
    parser = argparse.ArgumentParser(
        prog="protest history", description="Browse run history"
    )
    parser.add_argument(
        "--tail", "-n", type=int, default=10, help="Number of entries (default: 10)"
    )
    parser.add_argument("--model", type=str, default=None, help="Filter by model name")
    parser.add_argument("--suite", type=str, default=None, help="Filter by suite name")
    parser.add_argument("--runs", action="store_true", help="Show run-by-run list")
    parser.add_argument(
        "--show",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="N",
        help="Detailed panel for Nth most recent run (0=latest)",
    )
    parser.add_argument(
        "--compare", action="store_true", help="Compare 2 most recent runs"
    )
    parser.add_argument("--evals", action="store_true", help="Eval runs only")
    parser.add_argument("--tests", action="store_true", help="Test runs only")
    parser.add_argument(
        "--clean-dirty",
        action="store_true",
        help="Remove runs with uncommitted changes on current commit.",
    )
    parser.add_argument(
        "--path", type=str, default=None, help="History directory (default: .protest/)"
    )

    args = parser.parse_args(argv)
    history_dir = Path(args.path) if args.path else None

    if args.clean_dirty:
        removed = clean_dirty(history_dir=history_dir)
        print(
            f"Removed {removed} dirty entries."
            if removed
            else "No dirty entries to clean."
        )
        sys.exit(0)

    entries = load_history(
        history_dir=history_dir,
        model=args.model,
        suite=args.suite,
        evals_only=args.evals,
        tests_only=args.tests,
    )
    if not entries:
        print("No history found.")
        sys.exit(0)

    out = _get_output()
    if args.compare:
        if len(entries) < 2:
            print("Need at least 2 runs to compare.")
            sys.exit(1)
        out.compare(entries[-1], entries[-2])
    elif args.show is not None:
        idx = args.show
        if idx >= len(entries):
            print(f"Only {len(entries)} entries available.")
            sys.exit(1)
        out.detail(entries[-(idx + 1)])
    elif args.runs:
        out.runs(entries[-args.tail :])
    else:
        out.stats(entries)


# ---------------------------------------------------------------------------
# Output abstraction — Rich if available, plain text fallback
# ---------------------------------------------------------------------------


class _Output:
    """Base output — plain text."""

    def stats(self, entries: list[dict[str, Any]]) -> None:
        suites = _aggregate_suites(entries)
        if not suites:
            print("No suite data found.")
            return
        print(f"\n  {'Suite':<22} {'Kind':<6} {'Runs':>4}  {'Pass rate':<16} {'Flaky'}")
        for name in sorted(suites):
            s = suites[name]
            rate_str = _format_rate(s["pass_rates"])
            flaky_n = len(s["flaky"])
            print(
                f"  {name:<22} {s['kind']:<6} {s['n_runs']:>4}  {rate_str:<16} {flaky_n or ''}"
            )
        print()

    def runs(self, entries: list[dict[str, Any]]) -> None:
        for i, e in enumerate(entries):
            p, t, r = _entry_stats(e)
            git = (e.get("git") or {}).get("commit_short", "?")
            ts = e.get("timestamp", "?")[:16]
            print(f"\n  #{len(entries) - i:<3} {ts}  {p}/{t} ({r * 100:.0f}%)  {git}")
            for sn, sd in e.get("suites", {}).items():
                if not isinstance(sd, dict):
                    continue
                sp = sd.get("passed", 0)
                st = sd.get("total_cases", 0)
                sr = sp / st * 100 if st else 0
                model = sd.get("model") or "-"
                print(f"       {sn:<20} {sp}/{st} ({sr:.0f}%)  {model}")
        print()

    def detail(self, entry: dict[str, Any]) -> None:
        kind = "EVAL" if entry.get("evals") else "TEST"
        git = entry.get("git") or {}
        ts = entry.get("timestamp", "?")[:19]
        print(
            f"\n  {kind} run  {ts}  {git.get('commit_short', '?')} @ {git.get('branch', '?')}"
        )
        for sn, sd in entry.get("suites", {}).items():
            if not isinstance(sd, dict):
                continue
            suite_model = sd.get("model")
            model_str = f"  [{suite_model}]" if suite_model else ""
            print(
                f"\n  Suite: {sn}  {sd.get('passed', 0)}/{sd.get('total_cases', 0)}{model_str}"
            )
            for cn, cd in sd.get("cases", {}).items():
                if not isinstance(cd, dict):
                    continue
                m = "+" if cd.get("passed") else "-"
                print(f"    {m} {cn}  ({_fmt_dur(cd.get('duration', 0))})")
        print()

    def compare(self, current: dict[str, Any], previous: dict[str, Any]) -> None:
        cm = _get_display_model(current)
        pm = _get_display_model(previous)
        _, _, cr = _entry_stats(current)
        _, _, pr = _entry_stats(previous)
        if cm == pm:
            print(f"\n  Model: {cm}")
        else:
            print(f"\n  Model: {pm} → {cm}")
        print(f"  Pass rate: {pr * 100:.0f}% → {cr * 100:.0f}%")
        changes = _classify_changes(_all_cases(current), _all_cases(previous))
        _print_changes(changes)


class _RichOutput(_Output):
    """Rich output with colors, tables, panels."""

    def __init__(self) -> None:
        from rich.console import Console  # noqa: PLC0415 — optional dep

        self.console = Console(highlight=False)

    def stats(self, entries: list[dict[str, Any]]) -> None:
        from rich.table import Table  # noqa: PLC0415 — optional dep

        suites = _aggregate_suites(entries)
        if not suites:
            self.console.print("No suite data found.")
            return
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("Suite", min_width=12, no_wrap=True)
        table.add_column("Kind", width=5)
        table.add_column("Runs", justify="right", width=4)
        table.add_column("Pass rate", min_width=14, no_wrap=True)
        table.add_column("Scores", no_wrap=True)
        table.add_column("Flaky", width=5)

        for name in sorted(suites):
            s = suites[name]
            kind = s["kind"]
            kind_color = "cyan" if kind == "eval" else "blue"
            rate_str = _rich_rate(s["pass_rates"])
            score_arrows = _rich_score_arrows(s.get("score_values", {}))
            flaky_n = len(s["flaky"])
            flaky_str = f"[yellow]{flaky_n}[/]" if flaky_n else ""
            table.add_row(
                name,
                f"[{kind_color}]{kind}[/]",
                str(s["n_runs"]),
                rate_str,
                score_arrows,
                flaky_str,
            )

        self.console.print()
        self.console.print(table)
        self.console.print()

    def runs(self, entries: list[dict[str, Any]]) -> None:
        self.console.print()
        for i, e in enumerate(entries):
            p, t, r = _entry_stats(e)
            git = (e.get("git") or {}).get("commit_short", "?")
            ts = e.get("timestamp", "?")[:16]
            rate_color = "green" if r >= 0.8 else "yellow" if r >= 0.5 else "red"
            self.console.print(
                f"  [dim]#{len(entries) - i:<3}[/] {ts}  "
                f"[{rate_color}]{p}/{t} ({r * 100:.0f}%)[/]  [dim]{git}[/]"
            )
            for sn, sd in e.get("suites", {}).items():
                if not isinstance(sd, dict):
                    continue
                sp = sd.get("passed", 0)
                st = sd.get("total_cases", 0)
                sr = sp / st * 100 if st else 0
                sc = "green" if sr >= 80 else "yellow" if sr >= 50 else "red"
                model = sd.get("model") or "-"
                self.console.print(
                    f"       {sn:<20} [{sc}]{sp}/{st} ({sr:.0f}%)[/]  [cyan]{model}[/]"
                )
        self.console.print()

    def detail(self, entry: dict[str, Any]) -> None:
        from rich.panel import Panel  # noqa: PLC0415 — optional dep
        from rich.text import Text  # noqa: PLC0415 — optional dep

        kind = "EVAL" if entry.get("evals") else "TEST"
        git = entry.get("git") or {}
        ts = entry.get("timestamp", "?")[:19]
        evals_info = entry.get("evals") or {}

        lines = Text()
        lines.append(f"{kind} run", style="bold")
        lines.append(f"  {ts}  ", style="dim")
        lines.append(
            f"{git.get('commit_short', '?')} @ {git.get('branch', '?')}\n", style="dim"
        )

        # Scores summary
        for sn, stats in evals_info.get("scores_summary", {}).items():
            mean = stats.get("mean", 0)
            color = "green" if mean >= 0.8 else "yellow" if mean >= 0.5 else "red"
            lines.append(f"  {sn}: ", style="dim")
            lines.append(f"mean={mean:.2f}", style=color)
            lines.append(
                f"  p50={stats.get('median', 0):.2f}  p95={stats.get('p95', 0):.2f}\n",
                style="dim",
            )

        for sn, sd in entry.get("suites", {}).items():
            if not isinstance(sd, dict):
                continue
            p, t = sd.get("passed", 0), sd.get("total_cases", 0)
            lines.append("\nSuite: ", style="bold")
            lines.append(sn)
            pc = "green" if p == t else "yellow" if p >= t * 0.5 else "red"
            lines.append(f"  {p}/{t}", style=pc)
            suite_model = sd.get("model")
            if suite_model:
                lines.append(f"  [{suite_model}]", style="cyan")
            lines.append(f"  {_fmt_dur(sd.get('duration', 0))}\n", style="dim")
            for cn, cd in sd.get("cases", {}).items():
                if not isinstance(cd, dict):
                    continue
                if cd.get("passed"):
                    lines.append("  + ", style="green")
                else:
                    lines.append("  - ", style="red")
                lines.append(cn)
                lines.append(f"  ({_fmt_dur(cd.get('duration', 0))})\n", style="dim")

        self.console.print()
        self.console.print(
            Panel(lines, title="[bold]Run Detail[/]", border_style="cyan")
        )

    def compare(self, current: dict[str, Any], previous: dict[str, Any]) -> None:
        from rich.panel import Panel  # noqa: PLC0415 — optional dep
        from rich.text import Text  # noqa: PLC0415 — optional dep

        cm = _get_display_model(current)
        pm = _get_display_model(previous)
        _, _, cr = _entry_stats(current)
        _, _, pr = _entry_stats(previous)
        delta = cr - pr

        lines = Text()
        if cm == pm:
            lines.append(f"Model: {cm}\n", style="cyan")
        else:
            lines.append(f"Model: {pm} → {cm}\n", style="cyan")

        lines.append("Pass rate: ")
        lines.append(f"{pr * 100:.0f}%", style="dim")
        lines.append(" → ")
        rc = "green" if delta > 0 else "red" if delta < 0 else ""
        lines.append(f"{cr * 100:.0f}%", style=rc)
        if abs(delta) >= 0.001:
            lines.append(f" ({delta * 100:+.0f}%)", style=rc)
        lines.append("\n\n")

        changes = _classify_changes(_all_cases(current), _all_cases(previous))
        labels = [
            ("fixed", "Fixed", "green", "+"),
            ("regressed", "Regressions", "red", "-"),
            ("modified", "Modified", "yellow", "⟳"),
            ("new", "New", "cyan", "*"),
        ]
        has_any = False
        for key, label, color, marker in labels:
            items = changes[key]
            if items:
                has_any = True
                lines.append(f"{label} ({len(items)}):\n", style=color)
                for n in items:
                    lines.append(f"  {marker} {n}\n")
                lines.append("\n")
        if not has_any:
            lines.append("No changes.\n", style="dim")

        self.console.print()
        self.console.print(
            Panel(lines, title="[bold]Run Comparison[/]", border_style="cyan")
        )


def _get_output() -> _Output:
    try:
        return _RichOutput()
    except ImportError:
        return _Output()


# ---------------------------------------------------------------------------
# Rich helpers
# ---------------------------------------------------------------------------


def _rich_rate(rates: list[float]) -> str:
    if len(rates) >= 2:
        first, last = rates[0], rates[-1]
        delta = last - first
        if delta > 0.01:
            return f"[dim]{first * 100:.0f}%[/] [green]↗ {last * 100:.0f}%[/]"
        if delta < -0.01:
            return f"[dim]{first * 100:.0f}%[/] [red]↘ {last * 100:.0f}%[/]"
        return f"{last * 100:.0f}%"
    if rates:
        return f"{rates[0] * 100:.0f}%"
    return "-"


def _rich_score_arrows(score_values: dict[str, list[float]]) -> str:
    """Score trend arrows: ↗↘→ per score."""
    parts: list[str] = []
    for _name, values in sorted(score_values.items()):
        if len(values) >= 2:
            d = values[-1] - values[0]
            if d > 0.01:
                parts.append("[green]↗[/]")
            elif d < -0.01:
                parts.append("[red]↘[/]")
            else:
                parts.append("[dim]→[/]")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _format_rate(rates: list[float]) -> str:
    if len(rates) >= 2:
        first, last = rates[0], rates[-1]
        delta = last - first
        arrow = "↗" if delta > 0.01 else "↘" if delta < -0.01 else "→"
        return f"{first * 100:.0f}% {arrow} {last * 100:.0f}%"
    if rates:
        return f"{rates[0] * 100:.0f}%"
    return "-"


def _aggregate_suites(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    suites: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for name, data in entry.get("suites", {}).items():
            if not isinstance(data, dict):
                continue
            if name not in suites:
                suites[name] = {
                    "kind": data.get("kind", "test"),
                    "n_runs": 0,
                    "pass_rates": [],
                    "flaky": {},
                    "cases_seen": {},
                    "score_values": {},
                }
            s = suites[name]
            errored = data.get("errored", 0)
            total = data.get("total_cases", 0)
            passed = data.get("passed", 0)
            # Skip error-only runs (fixture crashes) from stats
            if errored and errored >= total:
                continue
            s["n_runs"] += 1
            if total:
                s["pass_rates"].append(passed / total)
            _track_cases(s, data.get("cases", {}))

    for s in suites.values():
        s["flaky"] = {
            cn: cs["fails"]
            for cn, cs in s["cases_seen"].items()
            if 0 < cs["fails"] < cs["runs"]
        }
    return suites


def _track_cases(suite: dict[str, Any], cases: dict[str, Any]) -> None:
    """Track per-case pass/fail and scores for a suite."""
    for cn, cd in cases.items():
        if not isinstance(cd, dict):
            continue
        # Skip errored cases (fixture crashes) from stats
        if cd.get("is_error"):
            continue
        if cn not in suite["cases_seen"]:
            suite["cases_seen"][cn] = {"runs": 0, "fails": 0}
        suite["cases_seen"][cn]["runs"] += 1
        if not cd.get("passed", True):
            suite["cases_seen"][cn]["fails"] += 1
        for sn, sv in cd.get("scores", {}).items():
            if isinstance(sv, (int, float)):
                if sn not in suite["score_values"]:
                    suite["score_values"][sn] = []
                suite["score_values"][sn].append(float(sv))


def _get_display_model(entry: dict[str, Any]) -> str:
    """Get display model: per-suite models if they differ, global otherwise."""
    suite_models = {
        sd.get("model")
        for sd in entry.get("suites", {}).values()
        if isinstance(sd, dict) and sd.get("model")
    }
    if len(suite_models) > 1:
        return ", ".join(sorted(suite_models))
    if suite_models:
        return next(iter(suite_models))
    return (entry.get("evals") or {}).get("model") or "-"


def _entry_stats(entry: dict[str, Any]) -> tuple[int, int, float]:
    total = passed = 0
    for data in entry.get("suites", {}).values():
        if isinstance(data, dict):
            total += data.get("total_cases", 0)
            passed += data.get("passed", 0)
    return passed, total, passed / total if total else 0


def _all_cases(entry: dict[str, Any]) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for data in entry.get("suites", {}).values():
        if isinstance(data, dict):
            cases.update(data.get("cases", {}))
    return cases


def _classify_changes(
    curr_cases: dict[str, Any],
    prev_cases: dict[str, Any],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "fixed": [],
        "regressed": [],
        "modified": [],
        "new": [],
    }
    for name, curr in curr_cases.items():
        prev = prev_cases.get(name)
        if prev is None:
            result["new"].append(name)
        elif curr.get("case_hash") and curr["case_hash"] != prev.get("case_hash"):
            result["modified"].append(f"{name} (case modified)")
        elif curr.get("eval_hash") and curr["eval_hash"] != prev.get("eval_hash"):
            result["modified"].append(f"{name} (scoring modified)")
        elif curr.get("passed") and not prev.get("passed"):
            result["fixed"].append(name)
        elif not curr.get("passed") and prev.get("passed"):
            result["regressed"].append(name)
    return result


def _print_changes(changes: dict[str, list[str]]) -> None:
    labels = {
        "fixed": ("Fixed", "+"),
        "regressed": ("Regressions", "-"),
        "modified": ("Modified", "⟳"),
        "new": ("New", "*"),
    }
    has_any = False
    for key, (label, marker) in labels.items():
        if changes[key]:
            has_any = True
            print(f"\n  {label} ({len(changes[key])}):")
            for n in changes[key]:
                print(f"    {marker} {n}")
    if not has_any:
        print("  No changes.")
    print()


def _fmt_dur(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{seconds % 60:.0f}s"
