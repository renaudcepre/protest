"""protest.console - progress output that bypasses test capture.

Usage::

    from protest import console

    @fixture()
    async def pipeline():
        for i, scene in enumerate(scenes):
            console.print(f"[bold]pipeline:[/] importing {scene.name} ({i+1}/{len(scenes)})")
            await import_scene(scene)

    # Raw mode - no markup processing
    console.print("debug: raw bytes here", raw=True)

    # Section mode - no per-test prefix (use for suite/session-level lines)
    console.print(f"  Results: {run_dir}", prefix=False)

Messages go through the event bus → reporters display them inline.
If no event bus is available (outside a protest session), falls back to stderr.
"""

from __future__ import annotations

import contextlib
import re

from protest.events.types import Event
from protest.execution.capture import get_event_bus, real_stderr


def print(msg: str, *, raw: bool = False, prefix: bool = True) -> None:
    """Print a message that bypasses test capture.

    Goes through the event bus so reporters display it at the right place.
    Supports Rich markup (stripped for ASCII reporter).

    Args:
        msg: The message to print. Supports Rich markup unless raw=True.
        raw: If True, no markup processing - message passed as-is.
        prefix: If False, omit the per-test indent/bar prefix. Use for
            suite-level or session-level lines (e.g. "Results: <dir>") that
            visually belong outside any single case's output block.
    """
    bus = get_event_bus()
    if bus is None:
        _fallback_print(msg, raw)
        return

    # Intentional private access to `bus._handlers`: we need sync dispatch
    # so messages appear immediately (not after the test). An earlier public
    # `EventBus.emit_sync` was removed (commit e14ffd5) because its signal-
    # handler use case was async-signal-unsafe, and we don't want to offer
    # that API to users. Kept private here - the framework itself is the
    # only caller, and console.print is never invoked from a signal handler.
    for handler_entry in bus._handlers.get(Event.USER_PRINT, []):
        try:
            handler_entry.func((msg, raw, prefix))
        except Exception as exc:
            # Surface handler failures (typically: malformed Rich markup) on
            # real stderr so users don't conclude `console.print` is silently
            # broken. Wrapped in suppress() to guarantee the loop continues
            # even if the fallback write itself raises.
            with contextlib.suppress(Exception):
                stream = real_stderr()
                stream.write(f"console.print: handler raised {exc!r}\n")
                stream.flush()


def _fallback_print(msg: str, raw: bool) -> None:
    """Fallback when no event bus - write to real stderr (bypassing capture)."""
    text = msg if raw else strip_markup(msg)
    stream = real_stderr()
    stream.write(text + "\n")
    stream.flush()


def strip_markup(msg: str) -> str:
    """Strip Rich markup tags from a string.

    Handles escaped brackets (``\\[text]`` → ``[text]``).
    """
    msg = msg.replace("\\[", "\x00")
    msg = re.sub(r"\[/?[^\]]*\]", "", msg)
    return msg.replace("\x00", "[")
