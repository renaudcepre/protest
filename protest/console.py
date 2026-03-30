"""protest.console — progress output that bypasses test capture.

Usage::

    from protest import console

    @fixture()
    async def pipeline():
        for i, scene in enumerate(scenes):
            console.print(f"[bold]pipeline:[/] importing {scene.name} ({i+1}/{len(scenes)})")
            await import_scene(scene)

    # Raw mode — no markup processing
    console.print("debug: raw bytes here", raw=True)

Messages go through the event bus → reporters display them inline.
If no event bus is available (outside a protest session), falls back to stderr.
"""

from __future__ import annotations

import contextlib
import re
import sys

from protest.events.types import Event
from protest.execution.capture import get_event_bus


def print(msg: str, *, raw: bool = False) -> None:
    """Print a message that bypasses test capture.

    Goes through the event bus so reporters display it at the right place.
    Supports Rich markup (stripped for ASCII reporter).

    Args:
        msg: The message to print. Supports Rich markup unless raw=True.
        raw: If True, no markup processing — message passed as-is.
    """
    bus = get_event_bus()
    if bus is None:
        _fallback_print(msg, raw)
        return

    # Call handlers directly (sync, bypasses async emit).
    # This ensures messages appear immediately, not after the test.
    for handler_entry in bus._handlers.get(Event.USER_PRINT, []):  # type: ignore[union-attr]
        with contextlib.suppress(Exception):
            handler_entry.func((msg, raw))


def _fallback_print(msg: str, raw: bool) -> None:
    """Fallback when no event bus — write to real stderr (bypassing capture)."""
    text = msg if raw else strip_markup(msg)
    # sys.stderr may be wrapped by TaskAwareStream — get the original
    stream = getattr(sys.stderr, "_original", sys.stderr)
    stream.write(text + "\n")
    stream.flush()


def strip_markup(msg: str) -> str:
    """Strip Rich markup tags from a string.

    Handles escaped brackets (``\\[text]`` → ``[text]``).
    """
    msg = msg.replace("\\[", "\x00")
    msg = re.sub(r"\[/?[^\]]*\]", "", msg)
    return msg.replace("\x00", "[")
