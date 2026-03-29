"""Metadata collection: git info, environment, CI detection."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any


def collect_git_info() -> dict[str, Any] | None:
    """Collect git context. Returns None if not in a git repo."""
    try:
        commit = _git("rev-parse", "HEAD")
        return {
            "commit": commit,
            "commit_short": commit[:7] if commit else None,
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain")),
            "author": _git("log", "-1", "--format=%an"),
            "commit_message": _git("log", "-1", "--format=%s"),
        }
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def collect_env_info() -> dict[str, Any]:
    """Collect environment metadata."""
    ci_provider = detect_ci_provider()
    return {
        "python_version": platform.python_version(),
        "protest_version": _get_pkg_version("protest"),
        "pydantic_evals_version": _get_pkg_version("pydantic-evals"),
        "hostname": platform.node(),
        "os": sys.platform,
        "ci": ci_provider is not None,
        "ci_provider": ci_provider,
    }


_CI_PROVIDERS: dict[str, str] = {
    "GITHUB_ACTIONS": "github-actions",
    "GITLAB_CI": "gitlab-ci",
    "CIRCLECI": "circleci",
    "BUILDKITE": "buildkite",
    "TRAVIS": "travis-ci",
}


def detect_ci_provider() -> str | None:
    """Detect CI provider from standard environment variables."""
    env = os.environ
    for var, name in _CI_PROVIDERS.items():
        if env.get(var) == "true":
            return name
    if env.get("JENKINS_URL"):
        return "jenkins"
    if env.get("CI") == "true":
        return "unknown"
    return None


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return result.stdout.strip()


def _get_pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None
