"""Module loading utilities for ProTest.

This module handles the infrastructure concern of loading Python modules
and extracting ProTestSession instances from them.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

from protest.entities import SuitePath

if TYPE_CHECKING:
    from protest.core.session import ProTestSession


class LoadError(Exception):
    """Error loading a session from a module."""


def parse_target(target: str) -> tuple[str, str | None]:
    """Parse extended target format into session target and optional suite filter.

    Args:
        target: Target string like 'module:session' or 'module:session::SuiteName'

    Returns:
        Tuple of (session_target, suite_filter).
        suite_filter is None if no suite path separator suffix present.

    Examples:
        'demo:session' -> ('demo:session', None)
        'demo:session::API' -> ('demo:session', 'API')
        'demo:session::API::Users' -> ('demo:session', 'API::Users')
    """
    sep = SuitePath.SEPARATOR
    if sep not in target:
        return target, None

    # Find first ":" (module:session separator)
    colon_idx = target.find(":")
    # Find suite separator after the first ":" (suite filter separator)
    double_colon_idx = target.find(sep, colon_idx + 1)
    if double_colon_idx == -1:
        return target, None

    session_target = target[:double_colon_idx]
    suite_filter = target[double_colon_idx + len(sep) :]
    return session_target, suite_filter


def load_session(target: str, app_dir: str = ".") -> ProTestSession:
    """Load a ProTestSession from a module path.

    Args:
        target: Module and session in format 'module.path:session_name'
        app_dir: Directory to add to sys.path for module lookup.

    Returns:
        The loaded ProTestSession instance.

    Raises:
        LoadError: If the target format is invalid, module not found,
                   session not found, or session is not a ProTestSession.
    """
    from protest.core.session import ProTestSession  # noqa: PLC0415

    if ":" not in target:
        raise LoadError(f"Invalid format '{target}'. Use 'module:session'")

    module_path, session_name = target.rsplit(":", 1)

    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise LoadError(f"Cannot import module '{module_path}': {exc}") from exc

    session = getattr(module, session_name, None)
    if session is None:
        raise LoadError(f"No '{session_name}' found in module '{module_path}'")

    if not isinstance(session, ProTestSession):
        raise LoadError(f"'{session_name}' is not a ProTestSession")

    return session
