from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

from protest import LoadError, ProTestSession, load_session


def unique_module_name() -> str:
    return f"test_module_{uuid.uuid4().hex[:8]}"


class TestLoadSessionTargetFormat:
    def test_missing_colon_raises_load_error(self) -> None:
        with pytest.raises(LoadError, match=r"Invalid format.*Use 'module:session'"):
            load_session("module_without_colon")

    def test_empty_target_raises_load_error(self) -> None:
        with pytest.raises(LoadError, match="Invalid format"):
            load_session("")


class TestLoadSessionModuleNotFound:
    def test_nonexistent_module_raises_load_error(self) -> None:
        with pytest.raises(LoadError, match="Cannot import module"):
            load_session("nonexistent_module_xyz:session")


class TestLoadSessionObjectNotFound:
    def test_session_not_in_module(self, tmp_path: Path) -> None:
        module_name = unique_module_name()
        module_file = tmp_path / f"{module_name}.py"
        module_file.write_text("x = 42\n")

        with pytest.raises(LoadError, match="No 'session' found in module"):
            load_session(f"{module_name}:session", app_dir=str(tmp_path))

    def test_object_is_not_protest_session(self, tmp_path: Path) -> None:
        module_name = unique_module_name()
        module_file = tmp_path / f"{module_name}.py"
        module_file.write_text("session = 'not a session'\n")

        with pytest.raises(LoadError, match="is not a ProTestSession"):
            load_session(f"{module_name}:session", app_dir=str(tmp_path))


class TestLoadSessionSuccess:
    def test_load_valid_session(self, tmp_path: Path) -> None:
        module_name = unique_module_name()
        module_file = tmp_path / f"{module_name}.py"
        module_file.write_text("""
from protest import ProTestSession

my_session = ProTestSession()

@my_session.test()
def test_example():
    assert True
""")

        session = load_session(f"{module_name}:my_session", app_dir=str(tmp_path))
        assert isinstance(session, ProTestSession)
        expected_test_count = 1
        assert len(session.tests) == expected_test_count

    def test_load_session_with_nested_module(self, tmp_path: Path) -> None:
        pkg_name = f"pkg_{uuid.uuid4().hex[:8]}"
        subdir = tmp_path / pkg_name
        subdir.mkdir()
        (subdir / "__init__.py").write_text("")
        (subdir / "tests.py").write_text("""
from protest import ProTestSession

session = ProTestSession()

@session.test()
def test_nested():
    pass
""")

        session = load_session(f"{pkg_name}.tests:session", app_dir=str(tmp_path))
        assert isinstance(session, ProTestSession)

    def test_load_session_custom_name(self, tmp_path: Path) -> None:
        module_name = unique_module_name()
        module_file = tmp_path / f"{module_name}.py"
        module_file.write_text("""
from protest import ProTestSession

custom_session_name = ProTestSession()
""")

        session = load_session(
            f"{module_name}:custom_session_name", app_dir=str(tmp_path)
        )
        assert isinstance(session, ProTestSession)


class TestLoadSessionAppDir:
    def test_app_dir_added_to_sys_path(self, tmp_path: Path) -> None:
        module_name = unique_module_name()
        module_file = tmp_path / f"{module_name}.py"
        module_file.write_text("""
from protest import ProTestSession
session = ProTestSession()
""")

        session = load_session(f"{module_name}:session", app_dir=str(tmp_path))
        assert isinstance(session, ProTestSession)

    def test_default_app_dir_is_current_directory(self) -> None:
        module_name = unique_module_name()
        module_file = Path(f"{module_name}.py")
        module_file.write_text("""
from protest import ProTestSession
session = ProTestSession()
""")
        try:
            session = load_session(f"{module_name}:session")
            assert isinstance(session, ProTestSession)
        finally:
            module_file.unlink()
            sys.modules.pop(module_name, None)
