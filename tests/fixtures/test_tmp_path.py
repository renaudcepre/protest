"""Tests for tmp_path builtin fixture."""

from pathlib import Path
from typing import Annotated

from protest import ProTestSession, Use, run_session, tmp_path


class TestTmpPath:
    def test_tmp_path_provides_path(self) -> None:
        """tmp_path fixture provides a Path object."""
        session = ProTestSession()
        received_path: Path | None = None

        @session.test()
        def test_receives_path(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            nonlocal received_path
            received_path = tmp

        result = run_session(session)

        assert result.success
        assert received_path is not None
        assert isinstance(received_path, Path)

    def test_tmp_path_is_directory(self) -> None:
        """tmp_path fixture provides an existing directory."""
        session = ProTestSession()
        was_directory = False

        @session.test()
        def test_is_dir(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            nonlocal was_directory
            was_directory = tmp.is_dir()

        result = run_session(session)

        assert result.success
        assert was_directory

    def test_tmp_path_allows_file_operations(self) -> None:
        """Can create and read files in tmp_path."""
        session = ProTestSession()

        @session.test()
        def test_file_ops(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            test_file = tmp / "test.txt"
            test_file.write_text("hello world")
            assert test_file.read_text() == "hello world"

        result = run_session(session)

        assert result.success

    def test_tmp_path_allows_nested_dirs(self) -> None:
        """Can create nested directories in tmp_path."""
        session = ProTestSession()

        @session.test()
        def test_nested(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            nested = tmp / "a" / "b" / "c"
            nested.mkdir(parents=True)
            assert nested.is_dir()

        result = run_session(session)

        assert result.success

    def test_tmp_path_cleaned_up_after_test(self) -> None:
        """tmp_path directory is cleaned up after test completes."""
        session = ProTestSession()
        captured_path: Path | None = None

        @session.test()
        def test_capture_path(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            nonlocal captured_path
            captured_path = tmp
            (tmp / "file.txt").write_text("content")

        result = run_session(session)

        assert result.success
        assert captured_path is not None
        assert not captured_path.exists(), "tmp_path should be cleaned up after test"

    def test_tmp_path_unique_per_test(self) -> None:
        """Each test gets its own tmp_path."""
        session = ProTestSession()
        paths: list[Path] = []

        @session.test()
        def test_one(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            paths.append(tmp)

        @session.test()
        def test_two(tmp: Annotated[Path, Use(tmp_path)]) -> None:
            paths.append(tmp)

        result = run_session(session)

        assert result.success
        assert len(paths) == 2
        assert paths[0] != paths[1], "Each test should get a unique tmp_path"
