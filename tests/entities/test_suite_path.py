"""Tests for SuitePath value object."""

import pytest

from protest.entities import SuitePath


class TestSuitePathCreation:
    def test_from_string(self) -> None:
        path = SuitePath("Parent::Child")
        assert str(path) == "Parent::Child"

    def test_from_parts(self) -> None:
        path = SuitePath.from_parts(["Parent", "Child", "GrandChild"])
        assert str(path) == "Parent::Child::GrandChild"

    def test_from_empty_parts(self) -> None:
        path = SuitePath.from_parts([])
        assert str(path) == ""

    def test_from_single_part(self) -> None:
        path = SuitePath.from_parts(["Single"])
        assert str(path) == "Single"


class TestSuitePathParts:
    def test_parts_nested(self) -> None:
        path = SuitePath("A::B::C")
        assert path.parts == ("A", "B", "C")

    def test_parts_single(self) -> None:
        path = SuitePath("Single")
        assert path.parts == ("Single",)

    def test_parts_empty(self) -> None:
        path = SuitePath("")
        assert path.parts == ()


class TestSuitePathAncestors:
    def test_ancestors_single(self) -> None:
        path = SuitePath("Single")
        ancestors = list(path.ancestors())
        assert len(ancestors) == 1
        assert str(ancestors[0]) == "Single"

    def test_ancestors_nested(self) -> None:
        path = SuitePath("A::B::C")
        ancestors = list(path.ancestors())
        assert len(ancestors) == 3
        assert str(ancestors[0]) == "A"
        assert str(ancestors[1]) == "A::B"
        assert str(ancestors[2]) == "A::B::C"

    def test_ancestors_empty(self) -> None:
        path = SuitePath("")
        ancestors = list(path.ancestors())
        assert ancestors == []


class TestSuitePathIsAncestorOf:
    def test_is_ancestor_of_self(self) -> None:
        path = SuitePath("A::B")
        assert path.is_ancestor_of(path)

    def test_is_ancestor_of_child(self) -> None:
        parent = SuitePath("A::B")
        child = SuitePath("A::B::C")
        assert parent.is_ancestor_of(child)

    def test_is_ancestor_of_grandchild(self) -> None:
        ancestor = SuitePath("A")
        descendant = SuitePath("A::B::C::D")
        assert ancestor.is_ancestor_of(descendant)

    def test_is_not_ancestor_of_sibling(self) -> None:
        path1 = SuitePath("A::B")
        path2 = SuitePath("A::C")
        assert not path1.is_ancestor_of(path2)

    def test_is_not_ancestor_of_unrelated(self) -> None:
        path1 = SuitePath("A::B")
        path2 = SuitePath("X::Y")
        assert not path1.is_ancestor_of(path2)

    def test_is_not_ancestor_partial_match(self) -> None:
        """Ensure 'A::B' is not ancestor of 'A::BC' (not a real child)."""
        path1 = SuitePath("A::B")
        path2 = SuitePath("A::BC")
        assert not path1.is_ancestor_of(path2)


class TestSuitePathChild:
    def test_child_from_non_empty(self) -> None:
        parent = SuitePath("A::B")
        child = parent.child("C")
        assert str(child) == "A::B::C"

    def test_child_from_empty(self) -> None:
        empty = SuitePath("")
        child = empty.child("Root")
        assert str(child) == "Root"


class TestSuitePathBool:
    def test_bool_empty_is_false(self) -> None:
        assert not SuitePath("")

    def test_bool_non_empty_is_true(self) -> None:
        assert SuitePath("A")
        assert SuitePath("A::B")


class TestSuitePathEquality:
    def test_equal_paths(self) -> None:
        assert SuitePath("A::B") == SuitePath("A::B")

    def test_unequal_paths(self) -> None:
        assert SuitePath("A::B") != SuitePath("A::C")

    def test_equality_with_different_type(self) -> None:
        assert SuitePath("A::B") != "A::B"


class TestSuitePathHashable:
    def test_can_be_used_in_set(self) -> None:
        paths = {SuitePath("A"), SuitePath("A::B"), SuitePath("A")}
        assert len(paths) == 2

    def test_can_be_used_as_dict_key(self) -> None:
        d = {SuitePath("A::B"): 1}
        assert d[SuitePath("A::B")] == 1


class TestSuitePathImmutable:
    def test_is_frozen(self) -> None:
        path = SuitePath("A::B")
        with pytest.raises(AttributeError):
            path._path = "C::D"  # type: ignore[misc]
